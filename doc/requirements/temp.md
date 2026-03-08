Hello! I hope your are fine! 

I need you to do something in my codebase! Please read doc/paper/sustainability-11-06965-v2.txt . The paper defines a building massing approach with substractive Geometry. If you read the src/ARCHITECTURE.md, you will see, thtat this codebase is designed to do that. 

The papers mentiones a column grid, or a grid , which spans accross the floor and guides the substractions. Currently the substractions are just done manually.

The floor data, currently doesnt have any grid information. src/models/building_grid.py implements the intial grid over the whole project. Now the necessary grid parts, need to be attached to the floor, so later, we can use the grid to create columns. Could you please think about a implementation witch merges the building_grid, the building_mass and the floor_data, so that each floor has an accessible grid after generation of the floor?

src/models/building_grid.py
src/models/building_mass.py
src/models/floor_data.py
src/models/grid_cell.py

Write your findings into