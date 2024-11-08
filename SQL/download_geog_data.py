from flask import Flask, jsonify, send_from_directory
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

def download_geod_data():
    url = "https://www2.mmm.ucar.edu/wrf/OnLineTutorial/CASES/SingleDomain/ungrib.php"
    response = requests.get(url)
    response.raise_for_status()

    # BeautifulSoup으로 HTML 파싱
    soup = BeautifulSoup(response.text, "html.parser")

    # 링크 추출
    download_link = soup.select_one("body > blockquote > blockquote > blockquote > p:nth-child(4) > p > a")
    if download_link:
        relative_file_url = download_link["href"]
        file_url = urljoin(url, relative_file_url)
        file_name = os.path.basename(relative_file_url)
        save_path = os.path.join(STATIC_DIR, file_name)

        # 파일 다운로드
        file_response = requests.get(file_url, stream=True)
        file_response.raise_for_status()

        with open(save_path, "wb") as f:
            for chunk in file_response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"파일이 다운로드되었습니다: {save_path}")
        
        # 파일 존재 여부 확인
        if os.path.exists(save_path):
            print(f"파일이 static 디렉토리에 저장되었습니다: {save_path}")
        else:
            print(f"파일 저장에 실패했습니다: {save_path}")
        
        return file_name
    else:
        print("다운로드 링크를 찾을 수 없습니다.")
        return None

@app.route('/')
def home():
    return jsonify({"message": "Welcome to the File Download GEOG Service. Use /GEOG to start the download."})

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico')

@app.route('/GEOG', methods=['GET'])
def download():
    # 비동기로 download_geod_data 함수를 실행
    future = executor.submit(download_geod_data)
    file_name = future.result()

    if file_name:
        return jsonify({"status": "success", "file_url": f"/static/{file_name}"})
    else:
        return jsonify({"status": "error", "message": "파일을 다운로드할 수 없습니다."}), 404

@app.route('/static/<path:filename>')
def serve_file(filename):
    return send_from_directory(STATIC_DIR, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
