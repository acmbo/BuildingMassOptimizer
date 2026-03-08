## Activate environment

conda activate pyocc

## User tests

python test/userInteraction/test_floorgeneration.py
python test/userInteraction/test_buildinggrid.py
python test/userInteraction/test_subtraction.py

conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py
conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py --seed 42 --no-original
conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py --save-dir /tmp


## Run general tests
conda run -n pyoccEnv python -m pytest test/Models/ -v
