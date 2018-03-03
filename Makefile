all:
	-apt-get update -y
	-apt-get install python3 -y
	python3 -m pip install pycosat
	python3 -OO -m compileall solve.py
