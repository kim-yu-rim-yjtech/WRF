from fastapi import FastAPI, Query, HTTPException, Request  
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import psycopg2
import xarray as xr
import matplotlib.pyplot as plt
import geopandas as gpd
import numpy as np
import base64
import os
import io
from matplotlib.gridspec import GridSpec
import matplotlib.animation as animation
import tempfile
from typing import List, Tuple
from contextlib import contextmanager
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from matplotlib.animation import PillowWriter


app = FastAPI(title="WRF Animation Viewer")

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory="templates")  # HTML 템플릿 폴더 설정

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
        self.bounds = self.gdf.total_bounds
        plt.switch_backend('Agg')
        self.temp_cmap = 'coolwarm'

    def get_db_data(self, timestamp: datetime) -> Tuple[xr.Dataset, str]:
        """DB에서 데이터를 가져와 xarray Dataset으로 변환"""
        conn = get_db_connection()
        if conn is None:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT nc_data FROM WRF_2024_01_NC WHERE timestamp = %s",
                    (timestamp,)
                )
                result = cursor.fetchone()
                
                if result is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No data found for timestamp: {timestamp}"
                    )

                with tempfile.NamedTemporaryFile(delete=False, suffix=".nc") as tmp_file:
                    tmp_file.write(result[0])
                    return xr.open_dataset(tmp_file.name), tmp_file.name
        finally:
            conn.close()

    def process_data(self, ds: xr.Dataset):
        """데이터셋에서 필요한 변수들을 추출하고 처리"""
        xlat = ds['XLAT'].isel(Time=0)
        xlong = ds['XLONG'].isel(Time=0)
        t2 = ds['T2'].isel(Time=0) - 273.15  # 섭씨 변환
        u = ds['U'].mean(dim='bottom_top').isel(Time=0)
        v = ds['V'].mean(dim='bottom_top').isel(Time=0)
        
        return xlat, xlong, t2, u, v

    def plot_frame(self, ax, xlat, xlong, t2, u, v, zoom_box=None):
        """단일 프레임 플롯"""
        # 기본 범위 설정
        if zoom_box is None:
            ax.set_xlim(self.bounds[0], self.bounds[2])
            ax.set_ylim(self.bounds[1], self.bounds[3])
        else:
            ax.set_xlim(zoom_box[0], zoom_box[2])
            ax.set_ylim(zoom_box[1], zoom_box[3])
        
        # 온도 컨투어
        levels = np.arange(-5.0, 10.0, 0.5)
        contour = ax.contourf(xlong, xlat, t2, cmap='coolwarm', levels=levels)
        
        # 바람 벡터
        stride = 3 if zoom_box is None else 1
        quiver = ax.quiver(xlong[::stride, ::stride], 
                          xlat[::stride, ::stride],
                          u[::stride, ::stride], 
                          v[::stride, ::stride],
                          scale=200, color='green')
        
        # 지형도 플롯
        self.gdf.plot(ax=ax, edgecolor='black', facecolor='none', linewidth=0.5)
        
        # 격자선 추가
        ax.grid(True, linestyle='--', alpha=0.5)
        
        return contour, quiver

    def create_animation(self, timestamps: List[datetime]) -> str:
            """Generates animation as a temporary GIF file and returns its path."""
            try:
                fig, ax = plt.subplots(figsize=(70, 70))
                processed_data = []
                
                with temporary_files() as temp_files:
                    for ts in timestamps:
                        ds, temp_file = self.get_db_data(ts)
                        temp_files.append(temp_file)
                        processed_data.append(self.process_data(ds))

                    def update(frame):
                        ax.clear()
                        xlat, xlong, t2, u, v = processed_data[frame]
                        contour, quiver = self.plot_frame(ax, xlat, xlong, t2, u, v)
                        ax.set_title(timestamps[frame].strftime('%Y-%m-%d %H:%M'))
                        return contour, quiver

                    # 임시 파일에 애니메이션 저장
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".gif") as tmp_file:
                        ani = animation.FuncAnimation(fig, update, frames=len(processed_data), interval=1000, blit=False)
                        ani.save(tmp_file.name, writer="pillow", fps=2)
                        plt.close(fig)

                        # GIF 파일 경로 반환
                        return tmp_file.name

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Animation creation failed: {str(e)}")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("animation.html", {"request": request})

@app.get("/wrf-result-animation", response_class=HTMLResponse)
async def generate_animation(
    request: Request,
    start_time: datetime = Query(..., description="Start time (YYYY-MM-DD HH:MM:SS)"),
    end_time: datetime = Query(..., description="End time (YYYY-MM-DD HH:MM:SS)")
):
    """WRF 결과 애니메이션 생성 API 엔드포인트"""
    if end_time <= start_time:
        raise HTTPException(
            status_code=400,
            detail="End time must be after start time"
        )

    processor = WRFDataProcessor()
    timestamps = [
        start_time + timedelta(hours=i)
        for i in range(int((end_time - start_time).total_seconds() / 3600) + 1)
    ]

    try:
        # 임시 파일에 애니메이션 생성
        animation_path = processor.create_animation(timestamps)
        
        # 파일을 읽어 Base64로 인코딩
        with open(animation_path, "rb") as f:
            image_base64_data = base64.b64encode(f.read()).decode("utf-8")
        
        # 임시 파일 삭제
        os.remove(animation_path)

        # HTML 템플릿에 인코딩된 애니메이션 전달
        return templates.TemplateResponse(
            "animation.html", 
            {
                "request": request,
                "image_base64": image_base64_data
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Animation generation failed: {str(e)}"
        )
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "wrf_result_db_plot:app",
        host="0.0.0.0",
        port=8888,
        reload=True
    )