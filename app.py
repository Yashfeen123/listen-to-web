from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
from gtts import gTTS
import os
import uuid
import sqlite3

app = Flask(__name__)

AUDIO_FOLDER = 'static/audio'
DB_NAME = 'database.db'
os.makedirs(AUDIO_FOLDER, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS podcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            audio_url TEXT NOT NULL,
            duration INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape_article():
    data = request.get_json()
    url = data.get('url', '').strip()
    lang_code = data.get('lang', 'en')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        title_tag = soup.find('h1')
        title = title_tag.get_text().strip() if title_tag else "Untitled Article"

        paragraphs = soup.find_all('p')
        text_content = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])

        if not text_content:
            return jsonify({'error': 'Could not extract sufficient text content from this URL.'}), 400

        words = text_content.split()
        word_count = len(words)
        reading_time = max(1, round(word_count / 200))

        sentences = [s.strip() for s in text_content.split('.') if len(s.strip()) > 40]
        takeaways = sentences[:3] if len(sentences) >= 3 else [text_content[:150]]

        audio_filename = f"{uuid.uuid4()}.mp3"
        audio_path = os.path.join(AUDIO_FOLDER, audio_filename)
        
        tts = gTTS(text=text_content[:3000], lang=lang_code, slow=False) 
        tts.save(audio_path)
        
        audio_url = f"/{audio_path}"

        # Save to SQLite Database (Only if it doesn't already exist to prevent duplicates)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM podcasts WHERE title = ?', (title,))
        existing = cursor.fetchone()
        
        if not existing:
            cursor.execute('INSERT INTO podcasts (title, audio_url, duration) VALUES (?, ?, ?)', 
                           (title, audio_url, reading_time))
            conn.commit()
            
        conn.close()

        return jsonify({
            'title': title,
            'text': text_content,
            'word_count': word_count,
            'reading_time': reading_time,
            'takeaways': takeaways,
            'audio_url': audio_url
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/podcasts', methods=['GET'])
def get_podcasts():
    search_query = request.args.get('q', '').strip()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if search_query:
        cursor.execute(
            'SELECT title, audio_url, duration FROM podcasts WHERE title LIKE ? ORDER BY id DESC', 
            (f'%{search_query}%',)
        )
    else:
        cursor.execute('SELECT title, audio_url, duration FROM podcasts ORDER BY id DESC')
        
    rows = cursor.fetchall()
    conn.close()

    podcasts = [{'title': row[0], 'audioUrl': row[1], 'duration': row[2]} for row in rows]
    return jsonify(podcasts)

if __name__ == '__main__':
    app.run(debug=True)