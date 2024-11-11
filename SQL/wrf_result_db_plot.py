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
from matplotlib.gridspec import GridSpec
import matplotlib.animation as animation
import tempfile
from typing import List, Tuple
from contextlib import contextmanager
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware

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
            conn.close()
            
    def process_timestamp_data(self, ds: xr.Dataset) -> dict:
        """단일 시점의 데이터 처리"""
        try:
            xlat = ds['XLAT'].isel(Time=0)
            xlong = ds['XLONG'].isel(Time=0)
            t2 = ds['T2'].isel(Time=0) - 273.15  # Kelvin to Celsius
            
            # Wind vector processing
            u = ds['U'].mean(dim='bottom_top').isel(Time=0)
            v = ds['V'].mean(dim='bottom_top').isel(Time=0)
            
            # Adjust staggered grid for wind vectors
            u_adj = 0.5 * (u[:, :-1] + u[:, 1:])
            v_adj = 0.5 * (v[:-1, :] + v[1:, :])
            
            return {
                'xlat': xlat,
                'xlong': xlong,
                't2': t2,
                'u': u_adj,
                'v': v_adj
            }
        except Exception as e:
            print(f"Data processing error: {e}")
            raise HTTPException(status_code=500, detail=f"Data processing failed: {str(e)}")

    def create_animation(self, timestamps: List[datetime], save_path: str = "/home/yurim2/WRF/SQL/animations") -> str:
        """Generates animation with multiple timestamps"""
        try:
            fig, ax = plt.subplots(figsize=(14, 12))
            print(f"총 {len(timestamps)}개의 파일을 처리합니다.")
            processed_data = []
            
            with temporary_files() as temp_files:
                for ts in timestamps:
                    ds, temp_file = self.get_db_data(ts)
                    temp_files.append(temp_file)
                    processed_data.append(self.process_timestamp_data(ds))
                print("애니메이션 생성 시작")
                
                # Set up the first frame's colorbar
                data = processed_data[0]
                contour = ax.contourf(
                    data['xlong'], data['xlat'], data['t2'],
                    cmap=self.temp_cmap, levels=np.arange(-5.0, 10.0, 0.5)
                )
                cbar = plt.colorbar(contour, ax=ax, label="Temperature (°C)")

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

                ani = animation.FuncAnimation(fig, update, frames=len(processed_data), interval=2000, blit = False)
                try:
                    save_file_path = os.path.join(save_path, f"wrf_animation_{timestamps[0].strftime('%Y%m%d_%H%M')}_{timestamps[-1].strftime('%Y%m%d_%H%M')}.gif")
                    print(f"애니메이션을 {save_file_path}에 저장 중...")
                    ani.save(save_file_path, writer="pillow", fps=2)
                    print(f"애니메이션 저장 완료: {save_file_path}")
                    return save_file_path
                except Exception as e:
                    print(f"애니메이션 저장 중 오류 발생: {str(e)}")  # 오류를 출력
                    raise HTTPException(status_code=500, detail=f"Animation creation failed: {str(e)}")

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
        image_base64_data = processor.create_animation(timestamps)
        return templates.TemplateResponse(
            "animation.html", 
            {
                "request": request,
                "image_base64_data": image_base64_data
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