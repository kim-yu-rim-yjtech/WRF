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

def download_ncar_data()
    # db에서 데이터 불러오기 => flask내 파일명이 존재하면 건너띄는 조건을 쿼리문에 추가 필요
    def select_data(output_dir): # output_dir을 flask로 수정이 필요?
        conn = get_db_connection()
        if conn is None:
            return None
        
        cursor = conn.cursor()
        try:
            query = """
            SELECT *
            FROM ncar_data"""
            
            cursor.execute(query)
            #### 코드 추가 필요
            # url = url_path
            # file_reponse = requests.get(url, stream = True)
            # file_response.raise_For_status()
            # with open(save_path, 'wb') as f:
                # for chunk if file_response.iter_content(chunk_size = 8192):
                    # f.write(chunk)
            # print(f'파일이 다운로드되었습니다: {save_path}')
            # 파일 존재 여부 확인
            # if os.path.exists(save_path):
            #     print(f"파일이 static 디렉토리에 저장되었습니다: {save_path}")
            # else:
            #     print(f"파일 저장에 실패했습니다: {save_path}")
            
            # return file_name
        # else:
            # print("다운로드 링크를 찾을 수 없습니다.")
            # return None
            
        except Exception as e:
            print('데이터 로드에 실패했습니다.')
        finally:
            cursor.close()
            conn.close()


@app.route('/')
def home():
    return jsonify({"message": "Welcome to the File Download NCAR Service. Use /NCAR to start the download."})

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico')

@app.route('/NCAR', methods=['GET'])
def download():
    # 비동기로 download_ncar_data 함수를 실행
    future = executor.submit(download_ncar_data)
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
