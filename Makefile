all:
	-apt-get update -y
	-apt-get install python3 -y
	git clone https://github.com/sat-group/open-wbo.git
	cd open-wbo && git reset --hard 89dd2fe2e6335c6a2674da4741e2bd19c98bb1e3 && make rs
	cd ..
	python3 -OO -m compileall solve.py
