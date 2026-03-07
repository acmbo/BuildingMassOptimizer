Hello, here you see a prototype for a massing algorithm for building. But it doesnt not work as inteneded.

I need the following:
1. The user enters a polygon and other inputs:
  - floor height
  - number of floors
2. The program needs to create a "InitialBuildingMass".
  2.1 You create a extrusion from the polygon with heigth = floor heigth
  2.2 for the next floor you make a copy of polygon and move the poylgon up the ZAxis a distance times * i (start i with 1) of the floorHeight. 
  2.3 After that you extrade the polygon by the distance of the floorheight again. 
  2.4 You incirea i = i +1 and do step 2.2 and 2.3 again, till i == number of floors.

Could you redo the floorgeneraion script, and make a seperate file, where i can test and visualize the script result with an example, similar to the current main function?

Put the test in test/userInteraction.

