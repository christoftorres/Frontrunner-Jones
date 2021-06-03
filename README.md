Frontrunner Jones
=================

A collection of tools to measure and analyze frontrunning attacks on the Ethereum blockchain. This repository also includes the data that was collected and evaluated during our study. Our paper can be found [here](https://arxiv.org/pdf/2102.03347.pdf).

## Quick Start

A container with all the dependencies can be found [here](https://hub.docker.com/r/christoftorres/frontrunner-jones/).

To run the container, please install docker and run:

``` shell
docker pull christoftorres/frontrunner-jones && docker run -m 16g --memory-swap="24g" -p 8888:8888 -it christoftorres/frontrunner-jones
```

To detect if a block contains insertion frontrunning attacks simply run inside the container the following commands:

``` shell
# Start MongoDB
mkdir -p /data/db
mongod --fork --logpath /var/log/mongod.log

# Run detection script
cd /root/scripts/detection/insertion
python3 insertion.py 10882755:10882755
```

To start the Jupyter notebook server, please run inside the container the following commands and then open up http://localhost:8888 on your browser:

``` shell
cd /root/scripts/analysis
jupyter notebook --port=8888 --no-browser --ip=0.0.0.0 --allow-root --NotebookApp.token='' --NotebookApp.password=''
```

Afterwards, 

## Custom Docker image build

``` shell
docker build -t frontrunner-jones .
docker run -m 16g --memory-swap="24g" -p 8888:8888 -it frontrunner-jones:latest
```

## Installation Instructions

### 1. Install MongoDB

##### MacOS

``` shell
brew tap mongodb/brew
brew install mongodb-community@4.4
```

For other operating systems follow the installation instructions on [mongodb.com](https://docs.mongodb.com/manual/installation/).

### 2. Install Python dependencies

``` shell
python3 -m pip install -r requirements.txt
```

## Running Instructions

:warning: **!! To detect displacement and suppression a connection to a fully synced archive node is required. !!**

Please update ```scripts/detection/utils/settings.py``` with the hostname and port number of your fully synced archive node accordingly.
More information on how to run an archive node can be found [here](https://docs.ethhub.io/using-ethereum/running-an-ethereum-node/#archive-nodes).

#### Detecting Displacement

``` shell
cd scripts/detection/displacement
# Examples
python3 displacement.py 10995886:10995886 # Honeypot 1
python3 displacement.py 10992692:10992703 # Honeypot 2
```

#### Detecting Insertion

``` shell
cd scripts/detection/insertion
# Examples
python3 insertion.py 10882755:10882755 # Uniswap V2
python3 insertion.py 9317713:9317713   # Uniswap V1
python3 insertion.py 10892526:10892526 # SushiSwap
python3 insertion.py 7100448:7100448   # Bancor
# Detect gas token usage
python3 gas_token_analysis.py
```

#### Detecting Suppression

``` shell
cd scripts/detection/suppression
# Examples
python3 suppression.py 6191896:6191912 # Fomo3D 1
python3 suppression.py 6391537:6391551 # Fomo3D 2
python3 suppression.py 6507761:6507777 # Fomo3D 3
# Detect campaigns 
python3 suppression_campaigns.py
```
