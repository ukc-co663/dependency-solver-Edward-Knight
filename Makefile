all:
	-apt-get update -y
	-apt-get install python3 -y
	python3 -m compileall solve.py