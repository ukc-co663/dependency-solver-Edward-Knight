all:
	-apt-get update -y
	-apt-get install python3 -y
	apt-get install python3-pip -y
	yes | pip3 install pycosat
	python3 -OO -m compileall solve.py
