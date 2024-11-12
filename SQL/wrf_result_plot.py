from flask import Flask, jsonify, send_from_directory
import psycopg2
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import xarray as xr
import matplotlib.pyplot as plt
import geopandas as gpd
import numpy as np
import tempfile
from typing import List, Tuple
from contextlib import contextmanager
import matplotlib.animation as animation

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
        return conn
    except Exception as e:
        print("데이터베이스 연결에 실패했습니다:", e)
    return None

@contextmanager
def temporary_files():
    """임시 파일들을 관리하는 context manager"""
    temp_files = []
    try:
        yield temp_files
    finally:
        for file in temp_files:
            try:
                os.remove(file)
            except OSError:
                pass
            
class WRFDataProcessor:
    def __init__(self, shapefile_path: str = "/home/yurim2/WRF/pohang_shp/pohang.shp"):
        self.shapefile_path = shapefile_path
        self.gdf = gpd.read_file(shapefile_path)
        plt.switch_backend('Agg')
        self.temp_cmap = 'coolwarm'
        
    def get_db_data(self, timestamp: datetime) -> Tuple[xr.Dataset, str]:
        """DB에서 데이터를 가져와 xarray Dataset으로 변환"""
        conn = get_db_connection()
        if conn is None:
            raise Exception("Database connection failed")
        
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT nc_data FROM WRF_2024_01_NC WHERE timestamp = %s",
                    (timestamp,)
                )
                result = cursor.fetchone()
                
                if result is None:
                    raise Exception(f"No data found for timestamp: {timestamp}")

                with tempfile.NamedTemporaryFile(delete=False, suffix=".nc") as tmp_file:
                    tmp_file.write(result[0])
                    return xr.open_dataset(tmp_file.name), tmp_file.name
        finally:
            conn.close()
            
    def process_timestamp_data(self, ds: xr.Dataset) -> dict:
        """단일 시점의 데이터 처리"""
        try:
            xlat = ds['XLAT'].isel(Time=0)
            xlong = ds['XLONG'].isel(Time=0)
            t2 = ds['T2'].isel(Time=0) - 273.15  # Kelvin to Celsius
            u = ds['U'].mean(dim='bottom_top').isel(Time=0)
            v = ds['V'].mean(dim='bottom_top').isel(Time=0)
            u_adj = 0.5 * (u[:, :-1] + u[:, 1:])
            v_adj = 0.5 * (v[:-1, :] + v[1:, :])
            return {'xlat': xlat, 'xlong': xlong, 't2': t2, 'u': u_adj, 'v': v_adj}
        except Exception as e:
            print(f"Data processing error: {e}")
            raise Exception(f"Data processing failed: {str(e)}")

    def create_animation(self, timestamps: List[datetime]) -> str:
        try:
            fig, ax = plt.subplots(figsize=(10, 10))
            print(f"총 {len(timestamps)}개의 파일을 처리합니다.")
            processed_data = []

            with temporary_files() as temp_files:
                for ts in timestamps:
                    ds, temp_file = self.get_db_data(ts)
                    temp_files.append(temp_file)
                    processed_data.append(self.process_timestamp_data(ds))
                
                def update(frame):
                    ax.clear()
                    data = processed_data[frame]
                    contour = ax.contourf(data['xlong'], data['xlat'], data['t2'], cmap=self.temp_cmap, levels=np.arange(-5.0, 10.0, 0.5))
                    ax.quiver(data['xlong'], data['xlat'], data['u'], data['v'], scale=300, color='green')
                    self.gdf.plot(ax=ax, edgecolor='black', facecolor='none')
                    ax.set_xlim(128.88, 129.6)
                    ax.set_ylim(35.82, 36.35)
                    ax.set_title(timestamps[frame].strftime('%Y-%m-%d %H:%M'))
                    return contour,

                ani = animation.FuncAnimation(fig, update, frames=len(processed_data), interval=2000, blit=False)
                save_file_path = os.path.join(STATIC_DIR, f"wrf_animation_{timestamps[0].strftime('%Y%m%d_%H%M')}_{timestamps[-1].strftime('%Y%m%d_%H%M')}.gif")
                ani.save(save_file_path, writer="pillow", fps=2)
                print(f"애니메이션 저장 완료: {save_file_path}")
                return save_file_path
        except Exception as e:
            print(f"애니메이션 저장 중 오류 발생: {str(e)}")
            raise Exception(f"Animation creation failed: {str(e)}")


wrf_processor = WRFDataProcessor()

@app.route('/')
def home():
    return jsonify({"message": "Welcome to the File Download wrf_result_plot Service. Use /RESULT to start the download."})

@app.route('/RESULT', methods=['GET'])
def result():
    timestamps = [datetime(2024, 1, 1, hour) for hour in range(6)]  # 예시 타임스탬프
    future = executor.submit(wrf_processor.create_animation, timestamps)
    return jsonify({"status": "in_progress", "message": "애니메이션 생성이 시작되었습니다. 생성된 애니메이션은 static 디렉토리에서 확인할 수 있습니다."})

@app.route('/static/result/<path:filename>')
def serve_file(filename):
    return send_from_directory(STATIC_DIR, filename)

@app.route('/downloaded_files', methods=['GET'])
def list_downloaded_files():
    files = os.listdir(STATIC_DIR)
    file_urls = [f"/static/{filename}" for filename in files]
    return jsonify({"status": "success", "files": file_urls})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5555, debug=True)
