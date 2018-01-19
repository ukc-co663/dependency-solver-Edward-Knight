all:
	-apt update
	-apt install python3
	python3 -m compileall solve.py