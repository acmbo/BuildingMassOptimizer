## Activate environment

conda activate pyocc

## User tests

python test/userInteraction/test_floorgeneration.py
python test/userInteraction/test_buildinggrid.py
python test/userInteraction/test_subtraction.py
python test/userInteraction/test_building_core.py

conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py
conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py --seed 42 --no-original
conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py --save-dir /tmp


# Interactive window (diagnostic style)
conda run -n pyoccEnv python test/userInteraction/test_pyvista_scene.py

# Architectural style
conda run -n pyoccEnv python test/userInteraction/test_pyvista_scene.py --style ARCHITECTURAL --save test/userInteraction/individuum_pyvista_archi.png

# Headless PNG export
conda run -n pyoccEnv python test/userInteraction/test_pyvista_scene.py --save test/userInteraction/individuum_pyvista.png


## Run general tests
conda run -n pyoccEnv python -m pytest test -v


## For claude
/home/acmbo/anaconda3/bin/conda run -n pyoccEnv python -m pytest test/ 
