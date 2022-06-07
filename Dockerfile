from ubuntu:20.04
label org.opencontainers.image.authors="Aaron Graubert"

run apt-get update -y && DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get install -y \
	python3 python3-pip vim tmux htop git build-essential && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    apt-get autoclean && \
    apt-get autoremove -y && \
    rm -rf /var/lib/{apt,dpkg,cache,log}/

run cd /opt && git clone https://gitlab.com/DavidGriffith/frotz.git && cd frotz && \
	make dumb && make install-dumb

env BEYMAX_CONFIG_PATH=/conf/config.yml BEYMAX_PERMISSIONS_PATH=/conf/permissions.yml BEYMAX_FIXME_DB_PKL_PATH=/var/beymax/db.pkl

copy games /games

copy ./requirements.txt /opt/beymax/

run python3 -m pip install --upgrade pip setuptools wheel && python3 -m pip install -r /opt/beymax/requirements.txt

copy . /opt/beymax

cmd python3 /opt/beymax/main.py
