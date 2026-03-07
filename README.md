conda activate pyocc

python test/userInteraction/test_floorgeneration.py
python test/userInteraction/test_buildinggrid.py

conda run -n pyoccEnv python -m pytest test/Models/ -v
