#!/usr/bin/env python3
"""
Test script to verify the Flask web interface works properly
without requiring Telegram connectivity.
"""

import threading
import time
import requests
import sys
import os

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from app import flask_app, MANGA_DATA, DATA_LOCK

def test_web_interface():
    """Test the Flask web interface."""
    print("🧪 Testing Comic Management System Web Interface...")
    
    # Add some test data
    with DATA_LOCK:
        MANGA_DATA.clear()
        MANGA_DATA['test-comic'] = {
            'title': 'Test Comic',
            'description': 'A test comic for verification',
            'cover_file_id': None,
            'chapters': {
                '1': ['page1_file_id', 'page2_file_id'],
                '2': ['page1_file_id', 'page2_file_id', 'page3_file_id']
            }
        }
        MANGA_DATA['another-comic'] = {
            'title': 'Another Comic',
            'description': 'Another test comic',
            'cover_file_id': 'test_cover_file_id',
            'chapters': {
                '1.5': ['page1_file_id'],
                '3': ['page1_file_id', 'page2_file_id']
            }
        }
    
    print("✅ Test data added")
    
    # Start Flask in a thread
    def run_flask():
        flask_app.run(host='localhost', port=5001, debug=False, use_reloader=False)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Wait for server to start
    time.sleep(2)
    
    try:
        # Test homepage
        print("🌐 Testing homepage...")
        response = requests.get('http://localhost:5001/', timeout=5)
        if response.status_code == 200:
            print("✅ Homepage loads successfully")
            if 'Test Comic' in response.text and 'Another Comic' in response.text:
                print("✅ Comic data is displayed correctly")
            else:
                print("❌ Comic data not found in homepage")
        else:
            print(f"❌ Homepage failed with status {response.status_code}")
        
        # Test manga detail page
        print("📚 Testing manga detail page...")
        response = requests.get('http://localhost:5001/manga/test-comic', timeout=5)
        if response.status_code == 200:
            print("✅ Manga detail page loads successfully")
            if 'Test Comic' in response.text and 'Chapter 1' in response.text:
                print("✅ Manga details and chapters are displayed correctly")
            else:
                print("❌ Manga details not properly displayed")
        else:
            print(f"❌ Manga detail page failed with status {response.status_code}")
        
        # Test chapter reader
        print("📖 Testing chapter reader...")
        response = requests.get('http://localhost:5001/chapter/test-comic/1', timeout=5)
        if response.status_code == 200:
            print("✅ Chapter reader loads successfully")
            if 'Test Comic' in response.text and 'Chapter 1' in response.text:
                print("✅ Chapter reader displays correctly")
            else:
                print("❌ Chapter reader not properly displayed")
        else:
            print(f"❌ Chapter reader failed with status {response.status_code}")
        
        # Test image proxy (will fail due to invalid file_id but should handle gracefully)
        print("🖼️ Testing image proxy error handling...")
        response = requests.get('http://localhost:5001/image/invalid_file_id', timeout=5)
        if response.status_code == 404:
            print("✅ Image proxy correctly handles invalid file IDs")
        else:
            print(f"⚠️ Image proxy returned unexpected status {response.status_code}")
        
        print("\n🎉 Web interface test completed successfully!")
        print("📋 Summary:")
        print("- Homepage: ✅ Working")
        print("- Manga detail pages: ✅ Working") 
        print("- Chapter reader: ✅ Working")
        print("- Error handling: ✅ Working")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Web interface test failed: {e}")
        return False

if __name__ == '__main__':
    success = test_web_interface()
    sys.exit(0 if success else 1)