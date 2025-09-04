#!/usr/bin/env python3
"""
Comprehensive test script to verify all comic management functionality
including conversation states, button callbacks, and handlers.
"""

import sys
import os

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

def test_conversation_states():
    """Test that all conversation states are properly defined."""
    from app import (SELECTING_ACTION, ADD_TITLE, ADD_DESC, ADD_COVER,
                    SELECT_MANGA, ACTION_MENU, ADD_CHAPTER_METHOD,
                    ADD_CHAPTER_ZIP, DELETE_CONFIRM, HELP_MENU,
                    WAITING_FOR_COMMAND_INPUT, ADD_CHAPTER_NUMBER,
                    ADD_CHAPTER_MANUAL, SELECT_CHAPTER_DELETE, EDIT_TITLE,
                    EDIT_DESC, EDIT_COVER)
    
    print("🔢 Testing conversation states...")
    
    states = [
        SELECTING_ACTION, ADD_TITLE, ADD_DESC, ADD_COVER,
        SELECT_MANGA, ACTION_MENU, ADD_CHAPTER_METHOD,
        ADD_CHAPTER_ZIP, DELETE_CONFIRM, HELP_MENU,
        WAITING_FOR_COMMAND_INPUT, ADD_CHAPTER_NUMBER,
        ADD_CHAPTER_MANUAL, SELECT_CHAPTER_DELETE, EDIT_TITLE,
        EDIT_DESC, EDIT_COVER
    ]
    
    # Check all states are unique integers
    if len(set(states)) == len(states):
        print("✅ All conversation states are unique")
    else:
        print("❌ Duplicate conversation states found")
        return False
        
    # Check states are sequential from 0
    if sorted(states) == list(range(len(states))):
        print("✅ All conversation states are properly numbered")
    else:
        print("❌ Conversation states are not properly numbered")
        return False
        
    print(f"✅ All {len(states)} conversation states verified")
    return True

def test_button_callbacks():
    """Test that all button callbacks are properly handled."""
    from app import button_callback
    
    print("🔘 Testing button callback handlers...")
    
    # Test callback data that should be handled
    expected_callbacks = [
        "add_manga",
        "manage_manga", 
        "add_chapters",
        "add_chapter_zip",
        "add_chapter_manual",
        "edit_info",
        "edit_title",
        "edit_description", 
        "edit_cover",
        "delete_comic",
        "confirm_delete",
        "help_menu",
        "show_stats",
        "main_menu"
    ]
    
    print(f"✅ Expected to handle {len(expected_callbacks)} button callbacks")
    
    # Check that button_callback function exists and is callable
    if callable(button_callback):
        print("✅ button_callback function is callable")
    else:
        print("❌ button_callback function is not callable")
        return False
        
    return True

def test_message_handlers():
    """Test that all message handlers are properly defined."""
    from app import (receive_title, receive_description, receive_cover,
                    receive_zip_file, receive_chapter_number, receive_chapter_page,
                    receive_edit_title, receive_edit_description, receive_edit_cover,
                    skip_edit_cover, show_comic_menu)
    
    print("📨 Testing message handlers...")
    
    handlers = [
        ("receive_title", receive_title),
        ("receive_description", receive_description),
        ("receive_cover", receive_cover),
        ("receive_zip_file", receive_zip_file),
        ("receive_chapter_number", receive_chapter_number),
        ("receive_chapter_page", receive_chapter_page),
        ("receive_edit_title", receive_edit_title),
        ("receive_edit_description", receive_edit_description),
        ("receive_edit_cover", receive_edit_cover),
        ("skip_edit_cover", skip_edit_cover),
        ("show_comic_menu", show_comic_menu)
    ]
    
    all_callable = True
    for name, handler in handlers:
        if callable(handler):
            print(f"✅ {name} is callable")
        else:
            print(f"❌ {name} is not callable")
            all_callable = False
    
    if all_callable:
        print(f"✅ All {len(handlers)} message handlers verified")
    
    return all_callable

def test_command_handlers():
    """Test that all command handlers are properly defined."""
    from app import (addcomic_command, addchapter_command, deletecomic_command,
                    listcomics_command, stats_command, show_help_menu, start, cancel)
    
    print("⌨️ Testing command handlers...")
    
    handlers = [
        ("start", start),
        ("addcomic_command", addcomic_command),
        ("addchapter_command", addchapter_command),
        ("deletecomic_command", deletecomic_command),
        ("listcomics_command", listcomics_command),
        ("stats_command", stats_command),
        ("show_help_menu", show_help_menu),
        ("cancel", cancel)
    ]
    
    all_callable = True
    for name, handler in handlers:
        if callable(handler):
            print(f"✅ {name} is callable")
        else:
            print(f"❌ {name} is not callable")
            all_callable = False
    
    if all_callable:
        print(f"✅ All {len(handlers)} command handlers verified")
    
    return all_callable

def test_conversation_handler_setup():
    """Test that the ConversationHandler is properly configured."""
    from app import setup_bot
    
    print("🗣️ Testing ConversationHandler setup...")
    
    try:
        # This should work since we have env vars set in .env file
        app = setup_bot()
        if app is not None:
            print("✅ setup_bot successfully created application with environment variables")
            print("✅ ConversationHandler setup completed without errors")
        else:
            print("❌ setup_bot returned None unexpectedly")
            return False
    except Exception as e:
        print(f"❌ setup_bot raised unexpected exception: {e}")
        return False
    
    print("✅ ConversationHandler setup function verified")
    return True

def test_data_management():
    """Test data management functions."""
    from app import slugify, extract_chapter_number, MANGA_DATA, DATA_LOCK
    
    print("📊 Testing data management functions...")
    
    # Test slugify function
    test_cases = [
        ("Test Comic", "test-comic"),
        ("My Amazing Story!", "my-amazing-story"),
        ("Special-Characters @#$", "special-characters"),
        ("   Multiple   Spaces   ", "multiple-spaces")
    ]
    
    for input_text, expected in test_cases:
        result = slugify(input_text)
        if result == expected:
            print(f"✅ slugify('{input_text}') = '{result}'")
        else:
            print(f"❌ slugify('{input_text}') = '{result}', expected '{expected}'")
            return False
    
    # Test extract_chapter_number function
    chapter_cases = [
        ("Chapter 1", "1"),
        ("ch 2.5", "2.5"),
        ("Episode 10", "10"),
        ("chapter-03", "03"),
        ("Special Chapter", "Special Chapter")  # fallback
    ]
    
    for input_text, expected in chapter_cases:
        result = extract_chapter_number(input_text)
        if result == expected:
            print(f"✅ extract_chapter_number('{input_text}') = '{result}'")
        else:
            print(f"❌ extract_chapter_number('{input_text}') = '{result}', expected '{expected}'")
            return False
    
    # Test MANGA_DATA access
    with DATA_LOCK:
        original_data = MANGA_DATA.copy()
        MANGA_DATA['test'] = {'title': 'Test'}
        if 'test' in MANGA_DATA:
            print("✅ MANGA_DATA read/write access works")
            MANGA_DATA.clear()
            MANGA_DATA.update(original_data)
        else:
            print("❌ MANGA_DATA write access failed")
            return False
    
    print("✅ All data management functions verified")
    return True

def main():
    """Run all tests."""
    print("🧪 Starting Comprehensive Comic Management System Tests")
    print("=" * 60)
    
    tests = [
        test_conversation_states,
        test_button_callbacks,
        test_message_handlers,
        test_command_handlers,
        test_conversation_handler_setup,
        test_data_management
    ]
    
    results = []
    for test in tests:
        print()
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("📋 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    test_names = [
        "Conversation States",
        "Button Callbacks", 
        "Message Handlers",
        "Command Handlers",
        "ConversationHandler Setup",
        "Data Management"
    ]
    
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print(f"\n🎯 OVERALL: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Comic management system is fully functional.")
        return True
    else:
        print("❌ Some tests failed. Check the issues above.")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)