# Procedural-city-generation

The objective is creting a fully procedurally generated 3D city model using Python and OpenGL

## 1.Features:
* Fully Generated 3D city model using Python and OpenGL
* Freeview camera able to fly anywhere on the map
* Textured skybox
* Textured buildings and roads of variable height
* Consistent performance no matter the scale of the city by utilizing display lists
* Building variety - a numbe of texture packs that would create a bigger variety in building heights
* Detailed streets - add further details at street level to make the roads more realistic
* Collision detection - the camera view sould still be able to travel freely around, but should not be able to phase through buildings or ground
* Consistent building sizes equal to real live building heights and sizes.
* Improved texture mapping to not allow for texture streching or distortion

## 2.Prerequisites:

| Requirement  | Details |
| ------------- | ------------- |
| Unix-based OS  | PyOpenGl is at the moment only supported on Unix-based machines  |
| Python 2.7  | The application was written using Python 2.7 and will not run correctly on newer versions  |
| PyOpenGL 3.1.0 and PyOpenGL_accelerate 3.1.0  |  The specified version of PyOpenGL will need to be installed onto the machine. There are further details on how to do that  |

All prerequisites can be installed through the command line by going to the trunk directory and typing : '$pip install -r requirements.txt'

## 3.How to run:

* From the command line run the application by navigating to the trunk folder and typing : 'python start_game'
* Once prompted, enter the number of rows and collumns you would like.
* To exit the application, either close the window or pressing "Esc"


## 4.Controls:

| Button  | Action |
| ------------- | ------------- |
| Esc  | exit application  |
| UP arrow  | move forwards  |
| BACK arrow | move backwards |
| LEFT arrow | move left  |
| RIGHT arrow | move right |
| D button | look fown |
| E button | look up |
| R button | reset camera to starting position |

## 5.Acknowledgements:

This project was from its outset intended to interface with the hardware and software infrastructure in the Networked Interaction Laboratory (NIL) in CSEE, which provides facilities for programs to display Stereoscopic output on its main displays and for interaction via a range of modalities, including gesture and bicycle. I would like to thank Dr Adrian Clark and Dr Louis Clift, who developed the infrastructure in the NIL, for making this straightforward to use.  Several resources were provided by Adrian Clark who I would like to acknowledge for his contribution. These include skybox textures and the NilGL Python package which makes adapting a conventional OpenGL + GLUT program into one that interfaces to the NIL infrastructure very simple to do and offers an implementation of camera movement as well as keyboard and mouse controller support. 
Lastly, the textures used for mapping both buildings and roads for this project have been provided by Sketchup Texture Club. The images have been referenced and have only been used for academic purposes. 
