from flask import Flask, jsonify, send_from_directory
import psycopg2
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor


app = Flask(__name__)

# static 디렉토리 설정
STATIC_DIR = os.path.join(app.root_path, 'static')
os.makedirs(STATIC_DIR, exist_ok=True)  # static 폴더가 없으면 생성

# 비동기 작업을 위한 ThreadPoolExecutor 설정
executor = ThreadPoolExecutor(max_workers=2)

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host="172.27.80.1",
            database="calpuff",
            user="postgres",
            password="1201"
        )
        print("데이터베이스에 연결되었습니다.")
        return conn
    except Exception as e:
        print("데이터베이스 연결에 실패했습니다:", e)
        return None

def download_grid2_data():
    conn = get_db_connection()
    
    if conn is None:
        return None
    
    cursor = conn.cursor()
    downloaded_files = []

    # 이미 다운로드된 파일 제외 조건
    query = """
    SELECT * 
    FROM ncar_data
    WHERE file_name NOT IN (SELECT file_name FROM downloaded_ncar_files)
    """
    cursor.execute(query)
    data = cursor.fetchall()
    
    if data:
        for row in data:
            _, time, file_name, url_path = row
            print("다운로드할 데이터:", row)
            download_path = os.path.join(STATIC_DIR, file_name)
            
            url_path = url_path.strip()
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}
            
            response = requests.get(url_path, headers=headers)
            if response.status_code == 200:
                with open(download_path, 'wb') as file:
                    file.write(response.content)
                
                cursor.execute("INSERT INTO downloaded_ncar_files (file_name) VALUES (%s)", (file_name,))
                conn.commit()
                downloaded_files.append(file_name)
                print(f"다운로드 완료: {file_name}")
            else:
                print("파일을 다운로드할 수 없습니다:", url_path, "상태 코드:", response.status_code)
    else:
        print("다운로드할 새로운 데이터가 없습니다.")
    
    cursor.close()
    conn.close()
    
    return downloaded_files

@app.route('/')
def home():
    return jsonify({"message": "Welcome to the File Download NCAR Service. Use /NCAR to start the download."})

@app.route('/NCAR', methods=['GET'])
def download():
    # 비동기로 download_ncar_data 함수를 실행
    future = executor.submit(download_grid2_data)

    # 비동기 실행 중 상태 메시지 반환
    return jsonify({"status": "in_progress", "message": "파일 다운로드가 시작되었습니다. 다운로드가 완료되면 파일을 static 디렉토리에서 확인할 수 있습니다."})


@app.route('/static/<path:filename>')
def serve_file(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route('/downloaded_files', methods=['GET'])
def list_downloaded_files():
    # 다운로드된 파일 목록을 확인하는 엔드포인트
    files = os.listdir(STATIC_DIR)
    file_urls = [f"/static/{filename}" for filename in files]
    return jsonify({"status": "success", "files": file_urls})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5555, debug=True)