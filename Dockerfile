FROM ubuntu:18.04

MAINTAINER Christof Torres (christof.torres@uni.lu)

SHELL ["/bin/bash", "-c"]
RUN apt-get update -q && \
    apt-get install -y \
    wget tar unzip pandoc python-setuptools python-pip python-dev python-virtualenv git build-essential software-properties-common python3-pip iputils-ping && \
    apt-get clean -q && rm -rf /var/lib/apt/lists/*

# Install MongoDB
ARG DEBIAN_FRONTEND=noninteractive
RUN wget -qO - https://www.mongodb.org/static/pgp/server-4.4.asc | apt-key add && echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu bionic/mongodb-org/4.4 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-4.4.list && apt-get update && apt-get install -y mongodb-org

# Install Python Dependencies
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt
RUN rm requirements.txt

WORKDIR /root
COPY scripts scripts
COPY data data

# Decompress data
RUN cd data && tar -xf displacement_results.tar.xz && rm displacement_results.tar.xz
RUN cd data && tar -xf insertion_results.tar.xz && rm insertion_results.tar.xz
RUN cd data && tar -xf insertion_gas_tokens.tar.xz && rm insertion_gas_tokens.tar.xz
RUN cd data && tar -xf suppression_campaigns.tar.xz && rm suppression_campaigns.tar.xz
RUN cd data && tar -xf suppression_results.tar.xz && rm suppression_results.tar.xz
