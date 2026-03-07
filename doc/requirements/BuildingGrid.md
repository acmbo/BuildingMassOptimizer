Great. Now i need a buildingrid. this works as follows:
  1. Create the AABB of the building mass. 
  2. This AABB needs to be split by a even grid on the axis x and y and the grid will be a aplied on each floor level. Se each cell will have z length of floorheigt, but an indivual x and y length computed through the AABB
  3, The Cell length should be computed in two ways, the user can determine:
     1. The user gives a fixed cell length
     2. the user gives a amount of cells value, and then you need to devide xyz accordingly.
Please create a Model class for the grid. Also create additional function in a pythonic way, if needed.

create a new visualization in test/userInteraction with the building mass similar to test/userInteraction/test_floorgeneration.py but also the grid, drawn in red for each floor
