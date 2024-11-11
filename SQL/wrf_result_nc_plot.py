from fastapi import FastAPI, Query, HTTPException, Request  
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import xarray as xr
import matplotlib.pyplot as plt
import geopandas as gpd
import numpy as np
import base64
import os
from matplotlib.gridspec import GridSpec
import matplotlib.animation as animation
import tempfile
from typing import List
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

class WRFDataProcessor:
    def __init__(self, 
                 data_dir: str = "/home/yurim2/WRF/SQL/", 
                 shapefile_path: str = "/home/yurim2/WRF/pohang_shp/pohang.shp"):
        self.data_dir = Path(data_dir)
        self.shapefile_path = shapefile_path
        self.gdf = gpd.read_file(shapefile_path)
        plt.switch_backend('Agg')
        
        self.temp_levels = np.arange(-15.0, 40.0, 0.5)
        self.temp_cmap = 'coolwarm'
    
    def _get_datetime_from_filename(self, filename: str) -> datetime:
        try:
            datetime_str = filename.split('wrfout_d01_')[1].replace(' ', '')  # Remove spaces
            return datetime.strptime(datetime_str, '%Y-%m-%d_%H:%M:%S')
        except Exception as e:
            print(f"Error parsing datetime from filename {filename}: {e}")
            return None

    def find_files_in_timerange(self, start_time: datetime, end_time: datetime) -> List[str]:
        all_files = sorted(self.data_dir.glob('wrfout_d01_*'))
        files_in_range = []
        
        for file_path in all_files:
            file_time = self._get_datetime_from_filename(file_path.name)
            if file_time and start_time <= file_time <= end_time:
                files_in_range.append(str(file_path))
        
        if not files_in_range:
            raise HTTPException(
                status_code=404,
                detail=f"No WRF files found between {start_time} and {end_time}"
            )
        
        return files_in_range

    def process_file_data(self, file_path: str) -> dict:
        try:
            ds = xr.open_dataset(file_path)
            xlat = ds['XLAT'].isel(Time=0)
            xlong = ds['XLONG'].isel(Time=0)
            t2 = ds['T2'].isel(Time=0) - 273.15
            
            u = ds['U'].mean(dim='bottom_top').isel(Time=0)
            v = ds['V'].mean(dim='bottom_top').isel(Time=0)
            u_adj = 0.5 * (u[:, :-1] + u[:, 1:])
            v_adj = 0.5 * (v[:-1, :] + v[1:, :])
            
            ds.close()
            
            return {
                'xlat': xlat,
                'xlong': xlong,
                't2': t2,
                'u': u_adj,
                'v': v_adj,
                'timestamp': self._get_datetime_from_filename(Path(file_path).name)
            }
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
            raise HTTPException(status_code=500, detail=f"Error processing WRF file: {str(e)}")

    def create_animation(self, start_time: datetime, end_time: datetime, save_path: str = "/home/yurim2/WRF/SQL/animations") -> str:
        try:
            wrf_files = self.find_files_in_timerange(start_time, end_time)
            print(f"Found {len(wrf_files)} files to process")

            if not wrf_files:
                raise HTTPException(
                    status_code=404,
                    detail="No data found for the specified time range"
                )
                
            fig = plt.figure(figsize=(14, 12))
            gs = GridSpec(1, 1)
            ax = fig.add_subplot(gs[0])

            print(f"총 {len(wrf_files)}개의 파일을 처리합니다.")
            processed_data = []
            for file_path in wrf_files:
                print(f"현재 파일: {file_path}")
                processed_data.append(self.process_file_data(file_path))
            print("애니메이션 생성 시작")

            # Add a colorbar only once, outside the update function
            first_data = processed_data[0]
            contour = ax.contourf(
                first_data['xlong'], 
                first_data['xlat'], 
                first_data['t2'],
                cmap='coolwarm',
                levels=np.arange(-5.0, 10.0, 0.5)
            )
            plt.colorbar(contour, ax=ax, label='기온 (°C)')

            def update(frame):
                ax.clear()
                data = processed_data[frame]
                
                contour = ax.contourf(
                    data['xlong'], 
                    data['xlat'], 
                    data['t2'],
                    cmap='coolwarm',
                    levels=np.arange(-5.0, 10.0, 0.5)
                )
                
                ax.quiver(
                    data['xlong'],  # 격자 간격 조정
                    data['xlat'],
                    data['u'],
                    data['v'],
                    scale=300,
                    color='black',
                    alpha=0.6
                )
                
                self.gdf.plot(ax=ax, edgecolor='black', facecolor='none')
                
                ax.set_xlim(128.88, 129.6)
                ax.set_ylim(35.82, 36.35)
                
                timestamp_str = data['timestamp'].strftime('%Y-%m-%d %H:%M')
                ax.set_title(f'포항 지역 기상 예측 - {timestamp_str}', fontsize=14, pad=20)
                
                ax.grid(True, linestyle='--', alpha=0.3)
                
                return contour,

            ani = animation.FuncAnimation(
                fig,
                update,
                frames=len(processed_data),
                interval=2000,
                blit=False
            )

            # Save to a specific path
            save_file_path = os.path.join(save_path, f"wrf_animation_{start_time.strftime('%Y%m%d_%H%M')}_{end_time.strftime('%Y%m%d_%H%M')}.gif")
            print("애니메이션 저장 중...")
            ani.save(
                save_file_path,
                writer='pillow',
                fps=2
            )
            print(f"애니메이션 저장 완료: {save_file_path}")
            
            return save_file_path

        except Exception as e:
            print(f"Animation creation error: {e}")
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
    
    try:
        image_base64_data = processor.create_animation(start_time, end_time)
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
        "wrf_result_nc_plot:app",
        host="0.0.0.0",
        port=8888,
        reload=True
    )