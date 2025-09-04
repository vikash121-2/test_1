import os
import sys
import threading
import logging
import requests
import asyncio
import zipfile
import tempfile
import re
import json
from pathlib import Path
from functools import wraps
from textwrap import dedent

# Add current directory to Python path for proper import
current_dir = os.path.dirname(os.path.abspath(__file__))
if (current_dir not in sys.path):
    sys.path.insert(0, current_dir)

from flask import Flask, render_template, redirect, url_for, abort
from dotenv import load_dotenv

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ParseMode

# --- CONFIGURATION (Globals) ---
TELEGRAM_TOKEN = None
ADMIN_USER_ID = None
CHANNEL_ID = None

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- IN-MEMORY DATA CACHE ---
MANGA_DATA = {}
MASTER_MESSAGE_ID = None
DATA_LOCK = threading.Lock()

# --- FLASK WEB APPLICATION ---
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    with DATA_LOCK:
        mangas_with_slugs = []
        for slug, manga_data in sorted(MANGA_DATA.items()):
            manga_with_slug = manga_data.copy()
            manga_with_slug['slug'] = slug
            mangas_with_slugs.append(manga_with_slug)
        mangas = sorted(mangas_with_slugs, key=lambda x: x['title'])
    return render_template("index.html", mangas=mangas)

@flask_app.route("/manga/<string:manga_slug>")
def manga_detail(manga_slug):
    with DATA_LOCK:
        manga_entry = MANGA_DATA.get(manga_slug)
    if not manga_entry: abort(404)
    try:
        chapters_sorted = sorted(manga_entry.get('chapters', {}).items(), key=lambda item: float(item[0]))
    except (ValueError, TypeError):
        chapters_sorted = sorted(manga_entry.get('chapters', {}).items())
    return render_template("manga_detail.html", manga=manga_entry, chapters=chapters_sorted, manga_slug=manga_slug)

@flask_app.route("/chapter/<string:manga_slug>/<string:chapter_num>")
def chapter_reader(manga_slug, chapter_num):
    with DATA_LOCK:
        manga_entry = MANGA_DATA.get(manga_slug)
    if not manga_entry or not manga_entry.get('chapters', {}).get(chapter_num): abort(404)
    chapter = {
        "manga_title": manga_entry['title'], "chapter_number": chapter_num,
        "pages": manga_entry['chapters'][chapter_num], "manga_slug": manga_slug
    }
    return render_template("chapter_reader.html", chapter=chapter)

@flask_app.route("/image/<file_id>")
def get_telegram_image(file_id):
    if not TELEGRAM_TOKEN: abort(500)
    try:
        api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
        response = requests.get(api_url)
        response.raise_for_status()
        file_path = response.json()['result']['file_path']
        image_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        return redirect(image_url)
    except Exception as e:
        logger.error(f"Failed to get image {file_id}: {e}")
        abort(404)

# --- TELEGRAM BOT LOGIC ---
# Enhanced conversation states for comprehensive functionality
(SELECTING_ACTION, ADD_TITLE, ADD_DESC, ADD_COVER,
 SELECT_MANGA, ACTION_MENU, ADD_CHAPTER_METHOD,
 ADD_CHAPTER_ZIP, DELETE_CONFIRM, HELP_MENU,
 WAITING_FOR_COMMAND_INPUT, ADD_CHAPTER_MANUAL,
 SELECT_CHAPTER_DELETE) = range(13)

def admin_only(func):
    """Decorator to check for admin access with enhanced error handling."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or user.id != ADMIN_USER_ID:
            logger.warning(f"Unauthorized access attempt by user {user.id if user else 'Unknown'} ({user.username if user else 'No username'}).")
            
            # Enhanced unauthorized message
            unauthorized_msg = "⛔️ **Access Denied**\n\nThis bot is restricted to authorized administrators only.\n\nIf you believe this is an error, please contact the bot owner."
            
            if update.callback_query: 
                await update.callback_query.answer("⛔️ Unauthorized access.", show_alert=True)
                await update.callback_query.edit_message_text(unauthorized_msg, parse_mode=ParseMode.MARKDOWN)
            elif update.message:
                await update.message.reply_text(unauthorized_msg, parse_mode=ParseMode.MARKDOWN)
            
            return ConversationHandler.END
        return await func(update, context, *args, **kwargs)
    return wrapped

def slugify(text):
    """Enhanced slugify function with better handling."""
    # Remove special characters, convert to lowercase, replace spaces with hyphens
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')

def extract_chapter_number(folder_name):
    """Extract chapter number from folder name with advanced pattern matching."""
    # Remove common prefixes and clean the name
    cleaned = re.sub(r'^(chapter|ch|episode|ep)[\s\-_]*', '', folder_name.lower())
    
    # Look for decimal numbers (like 1.5, 2.0, etc.)
    decimal_match = re.search(r'(\d+(?:\.\d+)?)', cleaned)
    if decimal_match:
        return decimal_match.group(1)
    
    # Fallback to just the folder name if no number found
    return folder_name

async def process_zip_chapters(context: ContextTypes.DEFAULT_TYPE, zip_file_content: bytes, manga_slug: str):
    """Process ZIP file and extract chapters with pages."""
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
            temp_zip.write(zip_file_content)
            temp_zip_path = temp_zip.name
        
        chapters_data = {}
        
        with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
            # Get all files in the zip
            all_files = zip_ref.namelist()
            
            # Group files by folder (chapter)
            chapters_folders = {}
            for file_path in all_files:
                if '/' in file_path and not file_path.endswith('/'):
                    folder_name = file_path.split('/')[0]
                    if folder_name not in chapters_folders:
                        chapters_folders[folder_name] = []
                    chapters_folders[folder_name].append(file_path)
            
            # Process each chapter folder
            for folder_name, files in chapters_folders.items():
                chapter_num = extract_chapter_number(folder_name)
                page_file_ids = []
                
                # Sort files naturally (page01.jpg, page02.jpg, etc.)
                files.sort(key=lambda x: [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', x)])
                
                for file_path in files:
                    # Check if it's an image file
                    if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                        try:
                            # Extract file from zip
                            file_data = zip_ref.read(file_path)
                            
                            # Send to Telegram to get file_id
                            message = await context.bot.send_document(
                                chat_id=CHANNEL_ID,
                                document=file_data,
                                filename=os.path.basename(file_path),
                                caption=f"Page for {manga_slug} Chapter {chapter_num}"
                            )
                            
                            # Get file_id
                            if message.document:
                                page_file_ids.append(message.document.file_id)
                            elif message.photo:
                                page_file_ids.append(message.photo[-1].file_id)
                                
                        except Exception as e:
                            logger.error(f"Failed to process file {file_path}: {e}")
                            continue
                
                if page_file_ids:
                    chapters_data[chapter_num] = page_file_ids
        
        # Clean up temp file
        os.unlink(temp_zip_path)
        
        return chapters_data
        
    except Exception as e:
        logger.error(f"Failed to process ZIP file: {e}")
        if 'temp_zip_path' in locals():
            try:
                os.unlink(temp_zip_path)
            except:
                pass
        return {}

async def save_data_to_channel(context: ContextTypes.DEFAULT_TYPE):
    """Enhanced data saving with better error handling and size management."""
    global MASTER_MESSAGE_ID
    
    try:
        with DATA_LOCK:
            if not MANGA_DATA:
                if MASTER_MESSAGE_ID:
                    try:
                        await context.bot.unpin_chat_message(chat_id=CHANNEL_ID, message_id=MASTER_MESSAGE_ID)
                        await context.bot.delete_message(chat_id=CHANNEL_ID, message_id=MASTER_MESSAGE_ID)
                        MASTER_MESSAGE_ID = None
                        logger.info("✅ Database cleared. Unpinned and deleted master message.")
                    except telegram.error.TelegramError as e:
                        logger.warning(f"⚠️ Failed to unpin/delete empty message (might already be gone): {e}")
                        MASTER_MESSAGE_ID = None
                return

            # Create formatted JSON with metadata
            data_with_metadata = {
                "version": "3.0",
                "last_updated": asyncio.get_event_loop().time(),
                "total_comics": len(MANGA_DATA),
                "total_chapters": sum(len(comic.get('chapters', {})) for comic in MANGA_DATA.values()),
                "data": MANGA_DATA
            }
            
            pretty_json = json.dumps(data_with_metadata, indent=2, ensure_ascii=False)
            
            # Enhanced size warning system
            if len(pretty_json) > 3500:  # Warning threshold
                logger.warning(f"⚠️ Database size approaching limit: {len(pretty_json)}/4096 characters")
                await context.bot.send_message(
                    chat_id=ADMIN_USER_ID, 
                    text=f"⚠️ **Database Size Warning**\n\nCurrent size: {len(pretty_json)}/4096 characters\nConsider archiving old comics if approaching the limit.",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            if len(pretty_json) > 4000:  # Critical threshold
                logger.error(f"❌ Database size critical: {len(pretty_json)}/4096 characters")
                await context.bot.send_message(
                    chat_id=ADMIN_USER_ID, 
                    text=f"🚨 **Critical Database Size**\n\nSize: {len(pretty_json)}/4096 characters\n\n**Action Required:** Delete some comics or chapters to prevent data loss!",
                    parse_mode=ParseMode.MARKDOWN
                )

            # Save data to channel
            try:
                if MASTER_MESSAGE_ID:
                    await context.bot.edit_message_text(
                        chat_id=CHANNEL_ID, 
                        message_id=MASTER_MESSAGE_ID, 
                        text=f"<code>{pretty_json}</code>", 
                        parse_mode=ParseMode.HTML
                    )
                    logger.info(f"✅ Updated master message {MASTER_MESSAGE_ID} successfully.")
                else:
                    message = await context.bot.send_message(
                        chat_id=CHANNEL_ID, 
                        text=f"<code>{pretty_json}</code>", 
                        parse_mode=ParseMode.HTML
                    )
                    MASTER_MESSAGE_ID = message.message_id
                    await context.bot.pin_chat_message(
                        chat_id=CHANNEL_ID, 
                        message_id=MASTER_MESSAGE_ID, 
                        disable_notification=True
                    )
                    logger.info(f"✅ Created and pinned new master message {MASTER_MESSAGE_ID}.")
                    
            except telegram.error.TelegramError as e:
                logger.error(f"❌ Failed to save to channel, attempting recovery: {e}")
                # Attempt to create new message
                try:
                    message = await context.bot.send_message(
                        chat_id=CHANNEL_ID, 
                        text=f"<code>{pretty_json}</code>", 
                        parse_mode=ParseMode.HTML
                    )
                    MASTER_MESSAGE_ID = message.message_id
                    await context.bot.pin_chat_message(
                        chat_id=CHANNEL_ID, 
                        message_id=MASTER_MESSAGE_ID, 
                        disable_notification=True
                    )
                    logger.info(f"✅ Recovery successful: Created new master message {MASTER_MESSAGE_ID}.")
                except telegram.error.TelegramError as recovery_error:
                    logger.critical(f"💥 Critical: Unable to save data to channel: {recovery_error}")
                    await context.bot.send_message(
                        chat_id=ADMIN_USER_ID,
                        text="🚨 **CRITICAL ERROR**\n\nUnable to save data to the channel!\nPlease check bot permissions and channel access.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
    except Exception as e:
        logger.critical(f"💥 Critical error in save_data_to_channel: {e}", exc_info=True)

# --- Enhanced Callback Query Handlers ---
@admin_only
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_manga":
        await query.edit_message_text(
            "📚 **Add New Comic**\n\nSend me the title of your new comic:",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADD_TITLE
    
    elif query.data == "manage_manga":
        with DATA_LOCK:
            if not MANGA_DATA:
                await query.edit_message_text(
                    "📚 **No Comics Found**\n\nYou haven't added any comics yet. Use 'Add New Comic' to get started!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                return SELECTING_ACTION
        
        keyboard = []
        for slug, manga in sorted(MANGA_DATA.items()):
            keyboard.append([InlineKeyboardButton(manga['title'], callback_data=f"select_{slug}")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")])
        
        await query.edit_message_text(
            "📚 **Select a Comic to Manage:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return SELECT_MANGA
    
    elif query.data.startswith("select_"):
        manga_slug = query.data[7:]  # Remove "select_" prefix
        context.user_data['selected_manga_slug'] = manga_slug
        
        with DATA_LOCK:
            manga = MANGA_DATA.get(manga_slug)
            if not manga:
                await query.edit_message_text("❌ Comic not found.")
                return SELECTING_ACTION
        
        chapter_count = len(manga.get('chapters', {}))
        
        keyboard = [
            [InlineKeyboardButton("➕ Add Chapter(s)", callback_data="add_chapters")],
            [InlineKeyboardButton("📝 Edit Info", callback_data="edit_info")],
            [InlineKeyboardButton("🗑️ Delete Comic", callback_data="delete_comic")],
            [InlineKeyboardButton("⬅️ Back", callback_data="manage_manga")]
        ]
        
        await query.edit_message_text(
            f'📚 **"{manga["title"]}"**\n\n📖 **Chapters:** {chapter_count}\n📝 **Description:** {manga.get("description", "No description")}\n\nWhat would you like to do?',
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return ACTION_MENU
    
    elif query.data == "add_chapters":
        keyboard = [
            [InlineKeyboardButton("📦 Upload ZIP File", callback_data="add_chapter_zip")],
            [InlineKeyboardButton("📄 Add Pages Manually", callback_data="add_chapter_manual")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"select_{context.user_data.get('selected_manga_slug', '')}")]
        ]
        
        await query.edit_message_text(
            "📖 **Add New Chapters**\n\nHow would you like to add chapters?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return ADD_CHAPTER_METHOD
    
    elif query.data == "add_chapter_zip":
        await query.edit_message_text(
            "📦 **Upload ZIP File**\n\nSend me a ZIP file containing your chapters.\n\n**Expected structure:**\n```\nchapters.zip\n├── Chapter 1/\n│   ├── page01.jpg\n│   ├── page02.jpg\n│   └── ...\n├── Chapter 2/\n│   ├── page01.jpg\n│   └── ...\n```\n\n⚡ **Tip:** Chapter numbers are auto-detected from folder names!",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADD_CHAPTER_ZIP
    
    elif query.data == "add_chapter_manual":
        context.user_data['chapter_pages'] = []
        context.user_data['current_chapter'] = None
        
        await query.edit_message_text(
            "📄 **Manual Chapter Addition**\n\nFirst, tell me the chapter number (e.g., '1', '2.5', '10'):",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADD_CHAPTER_MANUAL
    
    elif query.data == "delete_comic":
        manga_slug = context.user_data.get('selected_manga_slug')
        with DATA_LOCK:
            manga = MANGA_DATA.get(manga_slug)
            if manga:
                context.user_data['delete_manga_slug'] = manga_slug
                context.user_data['delete_manga_title'] = manga['title']
        
        keyboard = [
            [InlineKeyboardButton("🗑️ Yes, Delete Forever", callback_data="confirm_delete")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"select_{manga_slug}")]
        ]
        
        chapter_count = len(manga.get('chapters', {})) if manga else 0
        
        await query.edit_message_text(
            f'⚠️ **Delete Confirmation**\n\nAre you sure you want to delete:\n\n📚 **"{manga["title"]}"**\n📖 **{chapter_count} chapters**\n\n❗ This action cannot be undone!',
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return DELETE_CONFIRM
    
    elif query.data == "confirm_delete":
        manga_slug = context.user_data.get('delete_manga_slug')
        manga_title = context.user_data.get('delete_manga_title')
        
        if manga_slug:
            with DATA_LOCK:
                if manga_slug in MANGA_DATA:
                    del MANGA_DATA[manga_slug]
            
            await save_data_to_channel(context)
            
            await query.edit_message_text(
                f'✅ **Comic Deleted**\n\n"{manga_title}" has been permanently deleted from your website.',
                parse_mode=ParseMode.MARKDOWN
            )
            
            context.user_data.clear()
            
            # Return to main menu after 2 seconds
            await asyncio.sleep(2)
            return await start(update, context)
        
        return SELECTING_ACTION
    
    elif query.data == "help_menu":
        return await show_help_menu(update, context)
    
    elif query.data == "show_stats":
        return await show_statistics(update, context)
    
    elif query.data == "main_menu":
        context.user_data.clear()
        return await start(update, context)
    
    return SELECTING_ACTION

# --- Enhanced Message Handlers ---
@admin_only
async def receive_zip_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ZIP file upload for chapters."""
    if not update.message.document:
        await update.message.reply_text(
            "❌ **Invalid File**\n\nPlease send a ZIP file containing your chapters.",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADD_CHAPTER_ZIP
    
    file = update.message.document
    if not file.file_name.lower().endswith('.zip'):
        await update.message.reply_text(
            "❌ **Invalid File Type**\n\nPlease send a ZIP file (.zip extension).",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADD_CHAPTER_ZIP
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        "⏳ **Processing ZIP file...**\n\nThis may take a moment depending on the file size.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Download file
        telegram_file = await context.bot.get_file(file.file_id)
        file_content = await telegram_file.download_as_bytearray()
        
        # Process ZIP file
        manga_slug = context.user_data.get('selected_manga_slug')
        chapters_data = await process_zip_chapters(context, bytes(file_content), manga_slug)
        
        if not chapters_data:
            await processing_msg.edit_text(
                "❌ **Processing Failed**\n\nNo valid chapters found in the ZIP file. Please check the structure and try again.",
                parse_mode=ParseMode.MARKDOWN
            )
            return ADD_CHAPTER_ZIP
        
        # Add chapters to manga
        with DATA_LOCK:
            if manga_slug in MANGA_DATA:
                for chapter_num, pages in chapters_data.items():
                    MANGA_DATA[manga_slug]['chapters'][chapter_num] = pages
        
        await save_data_to_channel(context)
        
        # Success message
        chapter_list = ", ".join(chapters_data.keys())
        await processing_msg.edit_text(
            f'🎉 **Chapters Added Successfully!**\n\n📖 **Added chapters:** {chapter_list}\n📄 **Total pages:** {sum(len(pages) for pages in chapters_data.values())}\n\nThe chapters are now available on your website!',
            parse_mode=ParseMode.MARKDOWN
        )
        
        context.user_data.clear()
        
        # Return to main menu after 3 seconds
        await asyncio.sleep(3)
        return await start(update, context)
        
    except Exception as e:
        logger.error(f"Error processing ZIP file: {e}")
        await processing_msg.edit_text(
            f"❌ **Error Processing File**\n\nAn error occurred while processing the ZIP file: {str(e)[:100]}...",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADD_CHAPTER_ZIP

@admin_only
async def receive_chapter_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive chapter number for manual addition."""
    chapter_num = update.message.text.strip()
    context.user_data['current_chapter'] = chapter_num
    
    await update.message.reply_text(
        f'✅ **Chapter {chapter_num}**\n\nNow send me the pages for this chapter. You can send multiple images, and I\'ll add them in order.\n\nSend /done when you\'re finished adding pages.',
        parse_mode=ParseMode.MARKDOWN
    )
    return ADD_CHAPTER_MANUAL

@admin_only
async def receive_chapter_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive individual pages for manual chapter addition."""
    if update.message.text and update.message.text.strip().lower() == '/done':
        return await finish_manual_chapter(update, context)
    
    file_id = None
    
    # Handle different file types
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        # Check if it's an image document
        if update.message.document.mime_type and update.message.document.mime_type.startswith('image/'):
            file_id = update.message.document.file_id
    
    if file_id:
        if 'chapter_pages' not in context.user_data:
            context.user_data['chapter_pages'] = []
        
        context.user_data['chapter_pages'].append(file_id)
        page_count = len(context.user_data['chapter_pages'])
        
        await update.message.reply_text(
            f'✅ **Page {page_count} added**\n\nSend more pages or type /done to finish.',
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "❌ **Invalid File**\n\nPlease send an image file (photo or document).",
            parse_mode=ParseMode.MARKDOWN
        )
    
    return ADD_CHAPTER_MANUAL

async def finish_manual_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finish manual chapter addition."""
    chapter_num = context.user_data.get('current_chapter')
    pages = context.user_data.get('chapter_pages', [])
    manga_slug = context.user_data.get('selected_manga_slug')
    
    if not pages:
        await update.message.reply_text(
            "❌ **No Pages Added**\n\nYou haven't added any pages to this chapter.",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADD_CHAPTER_MANUAL
    
    # Add chapter to manga
    with DATA_LOCK:
        if manga_slug in MANGA_DATA:
            MANGA_DATA[manga_slug]['chapters'][chapter_num] = pages
    
    await save_data_to_channel(context)
    
    await update.message.reply_text(
        f'🎉 **Chapter {chapter_num} Added!**\n\n📄 **Pages:** {len(pages)}\n\nThe chapter is now available on your website!',
        parse_mode=ParseMode.MARKDOWN
    )
    
    context.user_data.clear()
    
    # Return to main menu after 2 seconds
    await asyncio.sleep(2)
    return await start(update, context)

@admin_only
async def receive_cover_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle document uploads for cover images."""
    if update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith('image/'):
        context.user_data['cover_file_id'] = update.message.document.file_id
        return await receive_cover(update, context)
    else:
        await update.message.reply_text(
            "❌ **Invalid File**\n\nPlease send an image file or type /skip to skip the cover image.",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADD_COVER

# --- Enhanced Text Command Handlers ---
async def addchapter_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /addchapter "Comic Title" command."""
    logger.info("📝 Processing /addchapter text command")
    
    # Extract title from command
    command_text = update.message.text
    title_match = re.search(r'/addchapter\s+"([^"]+)"', command_text)
    
    if not title_match:
        await update.message.reply_text(
            '❌ **Invalid Format**\n\nUse: `/addchapter "Comic Title"`\n\nExample: `/addchapter "My Amazing Comic"`',
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END
    
    title = title_match.group(1)
    
    # Find comic by title
    with DATA_LOCK:
        found_slug = None
        for slug, comic in MANGA_DATA.items():
            if comic['title'].lower() == title.lower():
                found_slug = slug
                break
    
    if not found_slug:
        await update.message.reply_text(
            f'❌ **Comic Not Found**\n\nNo comic found with title: "{title}"\n\nUse `/listcomics` to see all available comics.',
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END
    
    context.user_data['selected_manga_slug'] = found_slug
    context.user_data['selected_manga_title'] = title
    
    keyboard = [
        [InlineKeyboardButton("📦 Upload ZIP File", callback_data="add_chapter_zip")],
        [InlineKeyboardButton("📄 Add Pages Manually", callback_data="add_chapter_manual")],
        [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]
    ]
    
    await update.message.reply_text(
        f'✅ **Comic Found:** "{title}"\n\nHow would you like to add chapters?',
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ADD_CHAPTER_METHOD

async def deletecomic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /deletecomic "Comic Title" command."""
    logger.info("📝 Processing /deletecomic text command")
    
    # Extract title from command
    command_text = update.message.text
    title_match = re.search(r'/deletecomic\s+"([^"]+)"', command_text)
    
    if not title_match:
        await update.message.reply_text(
            '❌ **Invalid Format**\n\nUse: `/deletecomic "Comic Title"`\n\nExample: `/deletecomic "My Comic"`',
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END
    
    title = title_match.group(1)
    
    # Find comic by title
    with DATA_LOCK:
        found_slug = None
        for slug, comic in MANGA_DATA.items():
            if comic['title'].lower() == title.lower():
                found_slug = slug
                break
    
    if not found_slug:
        await update.message.reply_text(
            f'❌ **Comic Not Found**\n\nNo comic found with title: "{title}"',
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END
    
    context.user_data['delete_manga_slug'] = found_slug
    context.user_data['delete_manga_title'] = title
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Yes, Delete", callback_data="confirm_delete")],
        [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]
    ]
    
    chapter_count = len(MANGA_DATA[found_slug].get('chapters', {}))
    
    await update.message.reply_text(
        f'⚠️ **Delete Confirmation**\n\nAre you sure you want to delete:\n\n📚 **"{title}"**\n📖 **{chapter_count} chapters**\n\n❗ This action cannot be undone!',
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return DELETE_CONFIRM

async def addcomic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /addcomic "Title" command."""
    logger.info("📝 Processing /addcomic text command")
    
    # Extract title from command
    command_text = update.message.text
    title_match = re.search(r'/addcomic\s+"([^"]+)"', command_text)
    
    if not title_match:
        await update.message.reply_text(
            '❌ **Invalid Format**\n\nUse: `/addcomic "Comic Title"`\n\nExample: `/addcomic "My Amazing Comic"`',
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END
    
    title = title_match.group(1)
    context.user_data['title'] = title
    
    await update.message.reply_text(
        f'✅ **Comic Title Set:** "{title}"\n\nNow send me a description for this comic:',
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ADD_DESC

async def listcomics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /listcomics command."""
    with DATA_LOCK:
        if not MANGA_DATA:
            await update.message.reply_text("📚 No comics found in database.")
            return
        
        comics_list = []
        for i, (slug, comic) in enumerate(sorted(MANGA_DATA.items()), 1):
            chapter_count = len(comic.get('chapters', {}))
            comics_list.append(f"{i}. **{comic['title']}** ({chapter_count} chapters)")
        
        list_text = "📚 **All Comics:**\n\n" + "\n".join(comics_list)
        
        if len(list_text) > 4000:
            # Split into multiple messages if too long
            chunks = [comics_list[i:i+20] for i in range(0, len(comics_list), 20)]
            for i, chunk in enumerate(chunks):
                chunk_text = f"📚 **All Comics (Part {i+1}):**\n\n" + "\n".join(chunk)
                await update.message.reply_text(chunk_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(list_text, parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command."""
    with DATA_LOCK:
        if not MANGA_DATA:
            await update.message.reply_text("📊 **Statistics:** No data available.")
            return
            
        total_comics = len(MANGA_DATA)
        total_chapters = sum(len(comic.get('chapters', {})) for comic in MANGA_DATA.values())
        total_pages = sum(
            len(pages) for comic in MANGA_DATA.values() 
            for pages in comic.get('chapters', {}).values()
        )
        
        stats_text = f"""📊 **Quick Statistics**

📚 Comics: {total_comics}
📖 Chapters: {total_chapters}  
📄 Pages: {total_pages}

Use `/start` for detailed statistics and system info."""

        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

# --- Enhanced Conversation Handlers ---
@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Enhanced start function with comprehensive menu."""
    user = update.effective_user
    logger.info(f"👋 Admin {user.id} ({user.username}) started conversation.")
    
    # Get current stats
    with DATA_LOCK:
        total_comics = len(MANGA_DATA)
        total_chapters = sum(len(comic.get('chapters', {})) for comic in MANGA_DATA.values())
    
    keyboard = [
        [InlineKeyboardButton("➕ Add New Comic", callback_data="add_manga")],
        [InlineKeyboardButton("📚 Manage Existing Comics", callback_data="manage_manga")],
        [InlineKeyboardButton("❓ Help & Commands", callback_data="help_menu")],
        [InlineKeyboardButton("📊 Statistics", callback_data="show_stats")]
    ]
    
    welcome_text = f"""👋 **Welcome, Admin!**

🎯 **Your Advanced Serverless Comic CMS is ready**

📚 Comics: {total_comics}
📖 Chapters: {total_chapters}

🏗️ **Architecture Highlights:**
• Telegram Channel as Database
• Zero-cost serverless hosting
• Dual-mode reader (Long Strip/Paged)
• ZIP bulk upload support

Choose an option below or use text commands:
• `/addcomic "Title"` - Quick add comic
• `/addchapter "Title"` - Add chapters to existing comic
• `/deletecomic "Title"` - Delete a comic
• `/help` - Show all commands
• `/stats` - View statistics"""

    if update.callback_query:
        await update.callback_query.edit_message_text(
            welcome_text, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            welcome_text, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    return SELECTING_ACTION

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display comprehensive statistics."""
    with DATA_LOCK:
        if not MANGA_DATA:
            stats_text = "📊 **Statistics**\n\n📚 No comics added yet!"
        else:
            total_comics = len(MANGA_DATA)
            total_chapters = sum(len(comic.get('chapters', {})) for comic in MANGA_DATA.values())
            total_pages = sum(
                len(pages) for comic in MANGA_DATA.values() 
                for pages in comic.get('chapters', {}).values()
            )
            
            # Find comic with most chapters
            max_chapters_comic = max(
                MANGA_DATA.values(), 
                key=lambda x: len(x.get('chapters', {}))
            )
            max_chapters_count = len(max_chapters_comic.get('chapters', {}))
            
            # Calculate average pages per chapter
            avg_pages = total_pages / total_chapters if total_chapters > 0 else 0
            
            stats_text = f"""📊 **Advanced CMS Statistics**

🗄️ **Database Overview:**
📚 **Total Comics:** {total_comics}
📖 **Total Chapters:** {total_chapters}
📄 **Total Pages:** {total_pages}
📈 **Avg Pages/Chapter:** {avg_pages:.1f}

🏆 **Top Performer:**
   "{max_chapters_comic['title']}" ({max_chapters_count} chapters)

💾 **Database Status:** {'🟢 Healthy' if total_comics < 50 else '🟡 Large' if total_comics < 100 else '🔴 Very Large'}

🔧 **System Features:**
✅ Telegram Channel Database
✅ ZIP Bulk Upload
✅ Dual Reading Modes
✅ Auto Chapter Detection
✅ Document & Photo Support"""

    keyboard = [[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")]]
    
    await update.callback_query.edit_message_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return SELECTING_ACTION

async def show_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Enhanced help menu with comprehensive information."""
    help_text = """❓ **Advanced Serverless Comic CMS Help**

🏗️ **System Architecture:**
Your CMS uses a revolutionary serverless design powered by Telegram's infrastructure. All data is stored in your private channel as a single master JSON message, while images are stored directly on Telegram's servers.

🔘 **Button Interface:**
Use the intuitive menu buttons for guided workflows

📝 **Text Commands:**
• `/start` - Main menu
• `/addcomic "Title"` - Quick add comic
• `/addchapter "Comic Title"` - Add chapter to existing comic
• `/deletecomic "Comic Title"` - Delete a comic
• `/listcomics` - List all comics
• `/stats` - Show detailed statistics
• `/help` - This help menu
• `/cancel` - Cancel current operation

📦 **ZIP Upload Format:**
Structure your ZIP file like this:
```
chapters.zip
├── Chapter 1/
│   ├── page01.jpg
│   ├── page02.jpg
│   └── ...
├── Chapter 2.5/
│   ├── page01.jpg
│   └── ...
├── Special Chapter/
│   ├── page01.png
│   └── ...
```

🖼️ **Supported Formats:**
• **Photos:** JPG/JPEG (compressed)
• **Documents:** PNG, WebP, GIF (full quality)
• **ZIP Files:** For bulk chapter uploads

📱 **Reader Features:**
• **Long Strip Mode:** Vertical scrolling (default)
• **Paged Mode:** Traditional page-by-page reading
• **Keyboard Navigation:** Arrow keys in paged mode
• **Responsive Design:** Works on all devices

⚡ **Pro Tips:**
• Chapter numbers auto-detected from folder names
• Use decimal numbers for special chapters (e.g., "2.5")
• Send high-quality images as documents for best results
• The website updates instantly when you add content
• All data persists automatically in your Telegram channel"""

    keyboard = [
        [InlineKeyboardButton("🏗️ Architecture Info", callback_data="help_architecture")],
        [InlineKeyboardButton("📱 Reader Features", callback_data="help_reader")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    return SELECTING_ACTION

# --- Additional Message Handlers ---
@admin_only
async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive comic title."""
    title = update.message.text.strip()
    context.user_data['title'] = title
    
    await update.message.reply_text(
        f'✅ **Title Set:** "{title}"\n\nNow send me a description for this comic:',
        parse_mode=ParseMode.MARKDOWN
    )
    return ADD_DESC

@admin_only
async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive comic description."""
    description = update.message.text.strip()
    context.user_data['description'] = description
    
    await update.message.reply_text(
        f'✅ **Description Set**\n\nNow send me a cover image for this comic.\n\n💡 **Tip:** Send as a document for full quality, or as a photo for compressed version.\n\nType /skip to skip the cover image.',
        parse_mode=ParseMode.MARKDOWN
    )
    return ADD_COVER

@admin_only
async def receive_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive comic cover image."""
    if update.message.photo:
        # Get the highest quality photo
        photo = update.message.photo[-1]
        context.user_data['cover_file_id'] = photo.file_id
        cover_text = "✅ **Cover Image Set** (Photo - Compressed)"
    elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith('image/'):
        context.user_data['cover_file_id'] = update.message.document.file_id
        cover_text = "✅ **Cover Image Set** (Document - Full Quality)"
    else:
        context.user_data['cover_file_id'] = None
        cover_text = "ℹ️ **No Cover Image**"
    
    # Save the comic
    title = context.user_data['title']
    description = context.user_data['description']
    cover_file_id = context.user_data.get('cover_file_id')
    
    slug = slugify(title)
    
    with DATA_LOCK:
        MANGA_DATA[slug] = {
            'title': title,
            'description': description,
            'cover_file_id': cover_file_id,
            'chapters': {}
        }
    
    await save_data_to_channel(context)
    
    success_text = f"""🎉 **Comic Added Successfully!**

📚 **Title:** {title}
📝 **Description:** {description}
{cover_text}

🌐 **Your comic is now live on the website!**
✅ Ready for chapter uploads
✅ Supports ZIP bulk upload
✅ Dual-mode reader enabled"""

    keyboard = [[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")]]
    
    await update.message.reply_text(
        success_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Clear user data
    context.user_data.clear()
    return SELECTING_ACTION

@admin_only
async def skip_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip cover image."""
    context.user_data['cover_file_id'] = None
    return await receive_cover(update, context)

@admin_only
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current operation."""
    context.user_data.clear()
    
    cancel_text = "❌ **Operation Cancelled**\n\nReturning to main menu..."
    
    if update.callback_query:
        await update.callback_query.edit_message_text(cancel_text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(cancel_text, parse_mode=ParseMode.MARKDOWN)
    
    return await start(update, context)

# --- Bot Setup and Main ---
async def load_data_from_channel(application):
    """Load existing data from channel on startup."""
    global MASTER_MESSAGE_ID, MANGA_DATA
    
    try:
        # Get pinned messages from channel
        chat = await application.bot.get_chat(CHANNEL_ID)
        if (chat.pinned_message):
            MASTER_MESSAGE_ID = chat.pinned_message.message_id
            message_text = chat.pinned_message.text
            
            if message_text:
                try:
                    # Parse JSON data
                    data = json.loads(message_text)
                    if isinstance(data, dict) and 'data' in data:
                        MANGA_DATA = data['data']
                        logger.info(f"✅ Loaded {len(MANGA_DATA)} comics from channel.")
                    else:
                        MANGA_DATA = data
                        logger.info(f"✅ Loaded legacy data: {len(MANGA_DATA)} comics.")
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Failed to parse JSON data: {e}")
        else:
            logger.info("ℹ️ No pinned message found. Starting with empty database.")
            
    except Exception as e:
        logger.error(f"❌ Failed to load data from channel: {e}")

def setup_bot():
    """Setup and configure the Telegram bot."""
    global TELEGRAM_TOKEN, ADMIN_USER_ID, CHANNEL_ID
    
    # Load environment variables
    load_dotenv()
    
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', 0))
    CHANNEL_ID = os.getenv('CHANNEL_ID')
    
    if not all([TELEGRAM_TOKEN, ADMIN_USER_ID, CHANNEL_ID]):
        logger.critical("❌ Missing required environment variables!")
        return None
    
    # Create application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Setup enhanced conversation handler with all features
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('addcomic', addcomic_command),
            CommandHandler('addchapter', addchapter_command),
            CommandHandler('deletecomic', deletecomic_command),
            CommandHandler('listcomics', listcomics_command),
            CommandHandler('stats', stats_command),
            CommandHandler('help', show_help_menu),
        ],
        states={
            SELECTING_ACTION: [CallbackQueryHandler(button_callback)],
            ADD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
            ADD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_description)],
            ADD_COVER: [
                MessageHandler(filters.PHOTO, receive_cover),
                MessageHandler(filters.Document.IMAGE, receive_cover_document),
                CommandHandler('skip', skip_cover)
            ],
            SELECT_MANGA: [CallbackQueryHandler(button_callback)],
            ACTION_MENU: [CallbackQueryHandler(button_callback)],
            ADD_CHAPTER_METHOD: [CallbackQueryHandler(button_callback)],
            ADD_CHAPTER_ZIP: [MessageHandler(filters.Document.ZIP, receive_zip_file)],
            ADD_CHAPTER_MANUAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_chapter_number),
                MessageHandler(filters.PHOTO, receive_chapter_page),
                MessageHandler(filters.Document.IMAGE, receive_chapter_page)
            ],
            DELETE_CONFIRM: [CallbackQueryHandler(button_callback)]
        ],
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    application.add_handler(conv_handler)
    
    # Load data on startup
    application.job_queue.run_once(load_data_from_channel, when=1)
    
    return application

def run_flask():
    """Run Flask web server."""
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def main():
    """Main function to run both Flask and Telegram bot."""
    logger.info("🚀 Starting Comic Management System...")
    
    # Setup bot
    application = setup_bot()
    if not application:
        logger.critical("❌ Failed to setup bot. Exiting.")
        return
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("🌐 Flask web server started on http://localhost:5000")
    
    # Start bot
    logger.info("🤖 Starting Telegram bot...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()

