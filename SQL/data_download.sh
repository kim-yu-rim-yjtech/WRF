#!/bin/bash
exec 2>error_log_data_download.txt 
sudo apt update -y
sudo apt upgrade -y
sudo apt install -y gcc gfortran g++ libtool automake autoconf make m4 grads default-jre csh
sudo apt install -y expect

# 환경 변수 설정
export $(grep -v '^#' .env | xargs)

# 환경 변수 확인 (디버깅용)
echo "Current Environment: $ENV"
echo "HOME directory: $HOME"

# mkdir $HOME/WRF
cd $HOME/WRF
mkdir Downloads
mkdir Library

# 필요 라이브러리 다운로드
cd Downloads
wget -c https://www.zlib.net/fossils/zlib-1.2.13.tar.gz
wget -c https://docs.hdfgroup.org/archive/support/ftp/HDF5/releases/hdf5-1.10/hdf5-1.10.5/src/hdf5-1.10.5.tar.gz
wget -c https://downloads.unidata.ucar.edu/netcdf-c/4.9.0/netcdf-c-4.9.0.tar.gz
wget -c https://downloads.unidata.ucar.edu/netcdf-fortran/4.6.0/netcdf-fortran-4.6.0.tar.gz
wget -c http://www.mpich.org/static/downloads/3.3.1/mpich-3.3.1.tar.gz
wget -c https://download.sourceforge.net/libpng/libpng-1.6.37.tar.gz
wget -c https://www.ece.uvic.ca/~frodo/jasper/software/jasper-1.900.1.zip

export DIR=$HOME/WRF/Library
export CC=gcc
export CXX=g++
export FC=gfortran
export F77=gfortran

## zlib 설치
tar -xvzf zlib-1.2.13.tar.gz
cd zlib-1.2.13/
./configure --prefix=$DIR
make
make install

## HDF5 설치
cd $HOME/WRF/Downloads
tar -xvzf hdf5-1.10.5.tar.gz
cd hdf5-1.10.5/
./configure --prefix=$DIR --with-zlib=$DIR --enable-hl --enable-fortran
make check
make install

export HDF5=$DIR
export LD_LIBRARY_PATH=$DIR/lib:$LD_LIBRARY_PATH

## netCDF - c 설치
cd $HOME/WRF/Downloads
tar xvzf netcdf-c-4.9.0.tar.gz
cd netcdf-c-4.9.0
export CPPFLAGS=-I$DIR/include 
export LDFLAGS=-L$DIR/lib
./configure --prefix=$DIR --disable-dap
make check
make install

export PATH=$DIR/bin:$PATH
export NETCDF=$DIR

## netCDF - fortran 설치
cd $HOME/WRF/Downloads
tar -xvzf netcdf-fortran-4.6.0.tar.gz
cd netcdf-fortran-4.6.0/
export LD_LIBRARY_PATH=$DIR/lib:$LD_LIBRARY_PATH
export CPPFLAGS=-I$DIR/include 
export LDFLAGS=-L$DIR/lib
export LIBS="-lnetcdf -lhdf5_hl -lhdf5 -lz" 
./configure --prefix=$DIR --disable-shared
make check
make install

## MPICH 설치
cd $HOME/WRF/Downloads
tar -xvzf mpich-3.3.1.tar.gz
cd mpich-3.3.1/
./configure --prefix=$DIR
make
make install

## libpng 설치
cd $HOME/WRF/Downloads
export LDFLAGS=-L$DIR/lib
export CPPFLAGS=-I$DIR/include
tar -xvzf libpng-1.6.37.tar.gz
cd libpng-1.6.37/
./configure --prefix=$DIR
make
make install

## jasper 설치
cd $HOME/WRF/Downloads
sudo apt install unzip
sudo apt update
unzip jasper-1.900.1.zip
cd jasper-1.900.1/
autoreconf -i
./configure --prefix=$DIR
make
make install

export JASPERLIB=$DIR/lib
export JASPERINC=$DIR/include

# WRF 모델 설치
cd $HOME/WRF/
wget -c https://github.com/wrf-model/WRF/archive/v4.1.2.tar.gz
tar -xvzf v4.1.2.tar.gz -C $HOME/WRF
cd $HOME/WRF/WRF-4.1.2/
./clean

expect << EOF
spawn ./configure
expect "Enter selection" { send "34\r" } 
expect "Enter selection" { send "1\r" }  
EOF

./compile em_real 
export WRF_DIR=$HOME/WRF/WRF-4.1.2

# WPS 모델 설치
cd $HOME/WRF/
wget -c https://github.com/wrf-model/WPS/archive/v4.1.tar.gz
tar -xvzf v4.1.tar.gz -C $HOME/WRF
cd $HOME/WRF/WPS-4.1/

expect << EOF
spawn ./configure
expect "Enter selection" { send "3\r" }  
EOF

./compile

# geog 데이터 다운로드
cd $HOME/WRF/
mkdir WPS_GEOG
pip show requests &> /dev/null || pip install requests
pip show beautifulsoup4 &> /dev/null || pip install beautifulsoup4
pip show nest_asyncio &> /dev/null || pip install nest_asyncio
pip show asyncio &> /dev/null || pip install asyncio
pip show flask &? /dev/null || pip install flask
python3 $HOME/WRF/download_geog_data.py
mv $HOME/WRF/static/geog_data/geog_high_res_mandatory.tar.gz $HOME/WRF/WPS_GEOG


# grib2 데이터 다운로드
mkdir grib2_data
python $HOME/WRF/donload_ncar_data.py
mv $HOME/WRF/static/grib2_data $HOME/WRF/grib2_data