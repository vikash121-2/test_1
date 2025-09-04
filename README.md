# Advanced Serverless Comic CMS 🚀

A revolutionary comic/manga hosting platform that uses Telegram's infrastructure as a complete serverless backend. Zero hosting costs with enterprise-level features!

## 🏗️ Architecture Highlights

- **Telegram Channel as Database**: Your private channel stores all data as a single JSON message
- **Serverless Image Storage**: All images stored free on Telegram servers
- **Dual-Mode Reader**: Long Strip (webtoon) and Paged (traditional manga) modes
- **ZIP Bulk Upload**: Upload entire volumes with automatic chapter detection
- **Zero Infrastructure Costs**: No databases, no file storage, no server costs

## ✨ Features

### 🤖 Admin Control Panel (Telegram Bot)
- **Dual Interface**: Both button menus and text commands
- **Smart Content Management**: Add/delete comics and chapters
- **ZIP Processing**: Intelligent chapter extraction from folder structure
- **Image Format Support**: Photos (compressed) and Documents (full quality)
- **Real-time Statistics**: Database analytics and health monitoring

### 🌐 Public Website
- **Modern Dark Theme**: Responsive design with Tailwind CSS
- **Dual Reading Modes**: 
  - Long Strip: Seamless vertical scrolling
  - Paged: Traditional page-by-page with keyboard navigation
- **Instant Updates**: Website reflects changes immediately

### 📝 Text Commands
```
/start - Main admin menu
/addcomic "Title" - Quick add comic
/addchapter "Comic Title" - Add chapters to existing comic
/deletecomic "Comic Title" - Delete a comic
/listcomics - List all comics
/stats - Show statistics
/help - Comprehensive help
/cancel - Cancel any operation
```

## 🚀 Quick Start

### Prerequisites
1. **Telegram Bot**: Create via [@BotFather](https://t.me/botfather)
2. **Private Channel**: Create and add your bot as admin
3. **Your Telegram ID**: Get from [@userinfobot](https://t.me/userinfobot)

### Option 1: Google Colab (Recommended for Testing)

1. **Clone this repository**:
   ```python
   !git clone https://github.com/yourusername/advanced-comic-cms.git
   %cd advanced-comic-cms
   ```

2. **Install dependencies**:
   ```python
   !pip install -r requirements.txt
   ```

3. **Set up environment variables** in Colab:
   ```python
   import os
   os.environ['TELEGRAM_TOKEN'] = 'your_bot_token_here'
   os.environ['ADMIN_USER_ID'] = 'your_telegram_user_id'
   os.environ['CHANNEL_ID'] = 'your_channel_id'
   ```

4. **Run the application**:
   ```python
   !python app.py
   ```

5. **Access your site**: Use the provided Colab URL or ngrok tunnel

### Option 2: Heroku Deployment (Production)

1. **Prepare for Heroku**:
   ```bash
   git clone https://github.com/yourusername/advanced-comic-cms.git
   cd advanced-comic-cms
   ```

2. **Create Heroku app**:
   ```bash
   heroku create your-comic-cms-name
   ```

3. **Set environment variables**:
   ```bash
   heroku config:set TELEGRAM_TOKEN="your_bot_token"
   heroku config:set ADMIN_USER_ID="your_user_id"
   heroku config:set CHANNEL_ID="your_channel_id"
   ```

4. **Deploy**:
   ```bash
   git push heroku main
   ```

### Option 3: Local Development

1. **Clone and setup**:
   ```bash
   git clone https://github.com/yourusername/advanced-comic-cms.git
   cd advanced-comic-cms
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

3. **Run**:
   ```bash
   python app.py
   ```

## 📋 Setup Instructions

### 1. Create Your Telegram Bot
1. Message [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow instructions
3. Save your bot token

### 2. Create Database Channel
1. Create a **private channel** in Telegram
2. Add your bot as admin with these permissions:
   - Post Messages
   - Edit Messages
   - Delete Messages
   - Pin Messages

### 3. Get Channel ID
1. Post any message in your channel
2. Forward it to [@userinfobot](https://t.me/userinfobot)
3. Copy the Chat ID (negative number like `-1001234567890`)

### 4. Get Your User ID
1. Message [@userinfobot](https://t.me/userinfobot)
2. Copy your User ID

## 📦 ZIP Upload Format

Structure your comic chapters like this:

```
comic-volume-1.zip
├── Chapter 1/
│   ├── page01.jpg
│   ├── page02.jpg
│   └── page03.jpg
├── Chapter 2/
│   ├── page01.jpg
│   └── page02.jpg
├── Chapter 2.5/
│   └── special-page.png
└── Bonus Chapter/
    ├── bonus01.jpg
    └── bonus02.jpg
```

**Features:**
- ✅ Auto-detects chapter numbers from folder names
- ✅ Supports decimal chapters (1.5, 2.5)
- ✅ Natural sorting of pages
- ✅ Multiple image formats (JPG, PNG, WebP, GIF)

## 🔧 Technical Details

### Database Architecture
- **Master JSON Message**: Single pinned message in your channel
- **Atomic Updates**: All changes update the entire database
- **Version Control**: Metadata includes version and update timestamps
- **Size Monitoring**: Automatic warnings when approaching Telegram limits

### Image Storage
- **File IDs**: All images referenced by Telegram file_id
- **Proxy Routing**: Secure image serving without exposing bot token
- **Quality Options**: Support for both compressed photos and full-quality documents

### Reader Technology
- **Responsive Design**: Works on all screen sizes
- **Keyboard Navigation**: Arrow keys for paged mode
- **Smooth Scrolling**: Optimized long strip experience
- **Image Lazy Loading**: Fast page load times

## 🌍 Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_TOKEN` | Bot token from BotFather | `1234567890:ABCdef...` |
| `ADMIN_USER_ID` | Your Telegram user ID | `123456789` |
| `CHANNEL_ID` | Private channel ID | `-1001234567890` |

## 📊 Statistics & Monitoring

The system provides comprehensive analytics:
- Total comics, chapters, and pages
- Average pages per chapter
- Database size monitoring
- Top-performing comics
- System health indicators

## 🛠️ Troubleshooting

### Common Issues

**Bot doesn't respond:**
- Check if bot token is correct
- Ensure you're messaging the right bot
- Verify ADMIN_USER_ID matches your Telegram ID

**Can't save data:**
- Check if bot is admin in the channel
- Verify CHANNEL_ID is correct (negative number)
- Ensure bot has message permissions

**Images don't load:**
- Check if TELEGRAM_TOKEN is set correctly
- Verify image file_ids are valid
- Try re-uploading the images

### Getting Help

1. Check the `/help` command in your bot
2. Review the troubleshooting section
3. Check Heroku logs: `heroku logs --tail`
4. Open an issue on GitHub

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with Flask and python-telegram-bot
- UI powered by Tailwind CSS
- Inspired by the need for zero-cost comic hosting

---

**Made with ❤️ for the comic community**
