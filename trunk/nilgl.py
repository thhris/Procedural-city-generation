#!/usr/bin/env python
"""A set of useful routines for interactive with OpenGL models in the
Networked Interaction Lab (NIL) of the School of Computer Science and
Electronic Engineering of the University of Essex.

The purpose and operation of the software will be clearer if you have some
idea of the layout of the equipment in the NIL.  As the following illustration
shows, the viewer stands in front of a screen, which displays images that are
back-projected by a pair of projectors, driven by machines called "nil-left"
(left eye) and "nil-right" (right eye) and connected to a local (wired)
Ethernet.  The images projected are of 4096 x 2400 pixels and the
back-projection screen is 4.2 x 2.4 m; they are arranged to that their fields
of view are precisely superimposed.  The front of the left projector is
covered with a red filter and the front of the right projector has a green
filter; the viewer wears a pair of goggles with similarly-coloured filters so
that he or she is able to perceive the view as being stereoscopic.  There are
further displays around the NIL that give other views; for example, the left
side view is shown via a projector attached to the machine "nil-leftside".

  +---------------+---------------------+----------------------+
  |               |                     |             Ethernet |
  |        +-------------+         +--------------+            |
  |        |             |         |              |            |
  |        | left-server |         | right-server |            |
  |        |             |         |              |            |
  |        +-------------+         +--------------+            |
  |               |                     |                      |
  |               |                     |                      |
  |           +-------+             +-------+                  |
  |           |       |             |       |                  |
  |           | left  |             | right |                  |
  |           | proj  |             | proj  |                  |
  |           |       |             |       |                  |
  |           +-------+             +-------+                  |
  |             /   \                 /   \                    |
  |                                                            |
  |                                                            |
  |  ========================================================  |
  |                                                    screen  |
  |                                                            |
  |                                                            |
+--------------+                                       +---------------+
| nil-leftside |                                       | nil-rightside |
+--------------+            :   :                      +---------------+
       |                    :   :                              |
  +-----------+             :   :                        +------------+
  | left side |             : ^ :                        | right side |
  |  display  |             /   \                        |   display  |
  +-----------+           )|     |(  viewer              +------------+
                            \___/

In order to view the model steroscopically (or to obtain the view on the left
side display, etc), the same software must be running on each of the computers
that drives them; and any changes to the view of the model in light of
interaction or animation must take place synchronously in all copies of the
program.  This library provides facilities to achieve this by having the
programs make a network connection (across the wired Ethernet) to a central
machine and receive commands from it.  The software that distributes the
commands is called "nil-controller" and it runs on the machine "nil-command".

The viewer is able to interact with the model being viewed with a range of
devices.  All of these are interfaced, generally via a wireless LAN, to
machines running on the NIL network.  Each interaction device has a dedicated
client program whose purpose is to convert the input to a known form and
forward it to nil-controller.  nil-controller ascertains what effect that
interaction has on the view of the model, calculates what the new viewpoint in
the model will be, and then forwards it over the network to all the client
programs that drive the views of the model.  Transfer over the wired network
is so fast that any discrepancies in the update times on the different clients
is imperceptible.

This library provides principally the callback routines that OpenGL programs
use for interaction.  There are keyboard and mouse handlers that ensure
interaction with a program running locally is consistent with the same program
driving the NIL displays.  By adding a small number of calls to a program, it
will also be able to be used unchanged in the NIL, or to generate a movie from
a series of stored viewpoint positions.  If the model being viewed is able to
be loaded as a display list, the complete program to view and interact with it
need be only about one page of code.  The following callbacks are provided:

  reshape
  keybaord, special
  mouse, motion
  idle

In general, the only callback that a program needs to provide is the display
callback.

The vast majority of the work is done in the idle callback, which works in
concert with the routine "init" in this library.  The latter parses the
command line and sets variables within the library to tell the idle callback
provided by this library to read commands from the network (if the "-nil"
qualifier is given on the command line), to read commands from a file (if one
is provided on the command line), or simply to do nothing (when the program is
invoked without "-nil" or a filename).  The interpretation of commands is also
done by the idle callback.

Three ways of navigating in and around models are provided:

  FLY: movement commands affect the camera position directly.  In particular,
     rotations take place about the camera position.

  WALK: essentially the same as FLY but the y-value of position is not allowed
     to change.

  VIEW: rotations take place around the viewpoint rather than the camera
     position, so the observer can "look around" the viewpoint simply by
     rotating.

Built into this library is the ability to play scripts of commands: simply
invoke the program with "-play <file>" and it will play the commands in the
file, waiting for a specified pause between them.  You can set this pause (in
seconds, and fractions of a second are fine) from the command line too:
"-pause <secs>".  Note that the program deliberately busy-waits during these
pauses so that animations continue to play out -- don't be tempted to
'improve' the code by replacing the pauses with invocations of time.sleep().

Finally, please note that this software is under fairly continuous
development.  Please do not distribute it without the author's permission; his
contact details are at the foot of this file."""

#-------------------------------------------------------------------------------
# Boilerplate.
#-------------------------------------------------------------------------------
from __future__ import division
import argparse, copy, errno, os, random, select, socket
from PIL import Image
import string, sys, time
from math import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
from OpenGL.GL import *

#-------------------------------------------------------------------------------
# Global variables.
#-------------------------------------------------------------------------------
fov = 60                 # half the field-of-view of the OpenGL camera
near = 0.01              # near clipping distance
far = 2000               # far clipping distance

seed = random.random ()  # use a random seed unless one is supplied

CX, CY, CZ = (0, 0, 0)   # start at the origin...
VX, VY, VZ = (0, 0, 10)  # looking along the +z axis...
UX, UY, UZ = (0, 1, 0)   # with +y being upwards

default_angle = 1        # default rotation in degrees
default_step = 0.5       # default translation

iCX = iCY = iCZ = None   # initial viewpoint (used for "reset_viewpoint")
iVX = iVY = iVZ = iUX = iUY = iUZ = None

first_print_call = True  # output column headers on first "?" keystroke
pause = 0.0              # slug applications if > 0

idle_callback = None     # program's idle callback
keyboard_callback = None # program's keyboard callback
command_callback = None  # program's command-handling callback
cmd_table = {}           # command -> corresponding key
key_table = {}           # key -> corresponding command

motion_mode = "F"        # initial motion mode
motion_mode_names = {    # supported motion modes
    "F": "fly",
    "W": "walk",
    "V": "view"}

wait_until = 0           # filled when we're busy waiting for an animation

#-------------------------------------------------------------------------------
# Routines for registering callbacks.
#-------------------------------------------------------------------------------
def idlefunc (func):
    "Register an idle callback."
    global idle_callback
    idle_callback = func

def keyboardfunc (func):
    "Register a keyboard callback."
    global keyboard_callback
    keyboard_callback = func

def commandfunc (func):
    "Register a command callback."
    global command_callback
    command_callback = func

#-------------------------------------------------------------------------------
# Routines for saving rendered images of OpenGL models to files.
#-------------------------------------------------------------------------------
saving_mode = False
save_template = "frame-%5.5d.png"
save_frame_number = 0

def saving ():
    "Return the saving mode."
    global saving_mode
    return saving_mode

def set_saving_mode (state):
    "Set the saving mode."
    global saving_mode
    saving_mode = state

def frame_posted ():
    """Process a newly-displayed frame, intended to be called by the display
    callback after glutSwapBuffers."""
    global save_frame_number

    if saving () and save_frame_number > 0:
        save_frame ()
    save_frame_number += 1

def save_frame (format="PNG"):
    "Save the OpenGL window to a file."
    global window_width, window_height
    global save_template, save_frame_number

    glPixelStorei (GL_PACK_ALIGNMENT, 1)
    data = glReadPixels (0, 0, window_width, window_height, GL_RGB,
                         GL_UNSIGNED_BYTE)
    image = Image.frombytes ("RGB", (window_width, window_height), data)
    image = image.transpose (Image.FLIP_TOP_BOTTOM)
    filename = save_template % save_frame_number
    image.save (filename, format)
    print >>sys.stderr, "[saved %dx%d image to %s]" % \
        (window_width, window_height, filename)

#-------------------------------------------------------------------------------
# Routines to navigate through OpenGL models.
#-------------------------------------------------------------------------------
def get_viewpoint ():
    "Return the viewpoint, applying any global scale factor."
    global CX, CY, CZ, VX, VY, VZ, UX, UY, UZ, gsf
    return (CX*gsf, CY*gsf, CZ*gsf, VX*gsf, VY*gsf, VZ*gsf, UX, UY, UZ)

def reset_viewpoint ():
    "Reset the viewpoint to its initial value and re-enable fly mode."
    global CX, CY, CZ, VX, VY, VZ, UX, UY, UZ
    global iCX, iCY, iCZ, iVX, iVY, iVZ, iUX, iUY, iUZ
    CX = iCX
    CY = iCY
    CZ = iCZ
    VX = iVX
    VY = iVY
    VZ = iVZ
    UX = iUX
    UY = iUY
    UZ = iUZ
    fly_mode ()

def set_viewpoint (cx, cy, cz, vx, vy, vz, ux, uy, uz):
    "Set the viewpoint."
    global CX, CY, CZ, VX, VY, VZ, UX, UY, UZ
    global iCX, iCY, iCZ, iVX, iVY, iVZ, iUX, iUY, iUZ
    CX = cx
    CY = cy
    CZ = cz
    VX = vx
    VY = vy
    VZ = vz
    UX = ux
    UY = uy
    UZ = uz
    if not iCX:
        iCX = cx
        iCY = cy
        iCZ = cz
        iVX = vx
        iVY = vy
        iVZ = vz
        iUX = ux
        iUY = uy
        iUZ = uz

def get_gsf (v):
    "Return the global scale factor."
    global gsf
    return gsf

def set_gsf (v):
    "Set the global scale factor to v."
    global gsf
    gsf = v

def view_mode ():
    "Set motion to be in view mode."
    global motion_mode
    motion_mode = "V"

def fly_mode ():
    "Set motion to be in fly mode."
    global motion_mode
    motion_mode = "F"

def walk_mode ():
    "Set motion to be in walk mode."
    global motion_mode
    motion_mode = "W"

def set_translation_step (v):
    "Set the step size when translating."
    global default_step
    default_step = v

def get_translation_step ():
    "Get the step size when translating."
    global default_step
    return default_step

def set_rotation_step (v):
    "Set the step size when rotating."
    global default_angle
    default_angle = v

def get_rotation_step (v):
    "Get the step size when rotating."
    global default_angle
    return default_angle

def move_forward (dist):
    "Move the camera and viewpoint forward by an amount dist."
    global motion_mode
    global CX, CY, CZ, VX, VY, VZ, UX, UY, UZ

    dx = VX - CX
    dy = VY - CY
    dz = VZ - CZ
    veclen = sqrt (dx**2 + dy**2 + dz**2)
    fac = dist / veclen
    CX += fac * dx
    if motion_mode != "W": CY += fac * dy
    CZ += fac * dz
    VX += fac * dx
    if motion_mode != "W": VY += fac * dy
    VZ += fac * dz

def move_left (dist):
    "Move the camera sideways by an amount dist."
    global CX, CY, CZ, VX, VY, VZ, UX, UY, UZ

    dx = VX - CX
    dy = VY - CY
    dz = VZ - CZ
    veclen = sqrt (dx**2 + dy**2 + dz**2)
    lat = asin (dy / veclen)
    lon = atan2 (dz, dx)

    # "Sideways" is always 90 degrees away from the current longitude.
    direc = lon - pi / 2.0
    dxnew = cos (lat) * cos (direc)
    dznew = cos (lat) * sin (direc)

    CX += dxnew * dist
    CZ += dznew * dist
    VX += dxnew * dist
    VZ += dznew * dist

def move_up (dist):
    "Move the camera and viewpoint upward by an amount dist."
    global motion_mode
    global CX, CY, CZ, VX, VY, VZ, UX, UY, UZ

    if motion_mode != "W":
        CY += dist
        VY += dist

def rotate_vertically (angle):
    """Rotate the viewpoint vertically through angle DEGREES.  This
    will fail if we end up looking vertically."""
    global motion_mode
    global CX, CY, CZ, VX, VY, VZ, UX, UY, UZ

    angle = rad (angle)
    if motion_mode == "V":
        dx = CX - VX
        dy = CY - VY
        dz = CZ - VZ
        veclen = sqrt (dx**2 + dy**2 + dz**2)
        lat = asin (dy / veclen)
        Rcoslon = dx / cos (lat)
        dxnew = Rcoslon * cos (lat + angle)
        CX = VX + dxnew
        Rsinlon = dz / cos (lat)
        dznew = Rsinlon * cos (lat + angle)
        CZ = VZ + dznew
        CY = VY + veclen * sin (lat + angle)
    else:
        dx = VX - CX
        dy = VY - CY
        dz = VZ - CZ
        veclen = sqrt (dx**2 + dy**2 + dz**2)
        lat = asin (dy / veclen)
        Rcoslon = dx / cos (lat)
        dxnew = Rcoslon * cos (lat + angle)
        VX = CX + dxnew
        Rsinlon = dz / cos (lat)
        dznew = Rsinlon * cos (lat + angle)
        VZ = CZ + dznew
        VY = CY + veclen * sin (lat + angle)

def rotate_horizontally (angle):
    """Rotate the viewpoint horizontally through angle DEGREES.  This
    will fail if we are looking vertically."""
    global motion_mode
    global CX, CY, CZ, VX, VY, VZ, UX, UY, UZ

    angle = rad (angle)
    if motion_mode == "V":
        dx = CX - VX
        dy = CY - VY
        dz = CZ - VZ
        veclen = sqrt (dx**2 + dy**2 + dz**2)
        lat = asin (dy / veclen)
        lon = atan2 (dz, dx)
        dxnew = veclen * cos (lat) * cos (lon + angle)
        dznew = veclen * cos (lat) * sin (lon + angle)
        CX = VX + dxnew
        CZ = VZ + dznew
    else:
        angle = -angle     # so that +z -> +x if angle > 0
        dx = VX - CX
        dy = VY - CY
        dz = VZ - CZ
        veclen = sqrt (dx**2 + dy**2 + dz**2)
        lat = asin (dy / veclen)
        lon = atan2 (dz, dx)
        dxnew = veclen * cos (lat) * cos (lon + angle)
        dznew = veclen * cos (lat) * sin (lon + angle)
        VX = CX + dxnew
        VZ = CZ + dznew

def print_location (text="", f=sys.stdout):
    global motion_mode, motion_mode_names
    global CX, CY, CZ, VX, VY, VZ, UX, UY, UZ
    global first_print_call

    if first_print_call:
        print "%7s %7s %7s  %7s %7s %7s  %7s %7s %7s %s" % \
          ("CX", "CY", "CZ", "VX", "VY", "VZ", "UX", "UY", "UZ", "mode")
        first_print_call = False

    print "%7.2f %7.2f %7.2f  %7.2f %7.2f %7.2f  %7.2f %7.2f %7.2f %-7s %s" % \
    (CX, CY, CZ, VX, VY, VZ, UX, UY, UZ, motion_mode_names[motion_mode], text)

#-------------------------------------------------------------------------------
# OpenGL callback routines.
#-------------------------------------------------------------------------------
def reshape (w, h):
    "Work out how the view fits into the window."
    global window_width, window_height
    global fov, near, far
    window_width = w
    window_height = h
    glViewport (0, 0, w, h)
    glMatrixMode (GL_PROJECTION)
    glLoadIdentity ()
    f = fov / w * h   # a human is supposed to have a 120-degree FOV
    gluPerspective (f, w/h, near, far)
    glMatrixMode (GL_MODELVIEW)
    glLoadIdentity ()
    glutPostRedisplay ()

def print_keystrokes (f=sys.stdout):
    "Output the supported keystrokes."
    global cmd_table
    print >>f, "              TRANSLATION                          ROTATION"
    print >>f, ""
    print >>f, "                (up)  (forward)                      (up)"
    print >>f, "                   %s  %s                               %s" % \
      (cmd_table["move_up"], cmd_table["move_forward"], cmd_table["turn_up"])
    print >>f, "                   | /                                |"
    print >>f, "                   |/                                 |"
    print >>f, "      (left)  %s----+----%s  (right)" % \
      (cmd_table["move_left"], cmd_table["move_right"]),
    print >>f, "      (left)  %s----+----%s  (right)" % \
      (cmd_table["turn_left"], cmd_table["turn_right"])
    print >>f, "                  /|                                  |"
    print >>f, "                 / |                                  |"
    print >>f, "                %s  %s                                  %s" % \
      (cmd_table["move_backward"], cmd_table["move_down"],
       cmd_table["turn_down"])
    print >>f, "       (backward)  (down)                          (down)"
    print >>f, ""
    print >>f, "  F  fly navigation mode          +  increase step size by 10%"
    print >>f, "  W  walk navigation mode         -  decrease step size by 10%"
    print >>f, "  V  view navigation mode         <  increase angle step by 10%"
    print >>f, "  R  reset                        >  decrease angle step by 10%"
    print >>f, "  H  print this help              ?  print viewpoint"
    print >>f, "  q  exit"

def keyboard (key, x, y):
    "Handle keyboard events."
    # This routine needs to be modified to cope with user-defined keystrokes
    # in addition to the NIL-standard ones.  These keystrokes need to be read
    # from an external file, so that the same ones are available to the NIL
    # keyboard client as well as individual programs.
    global default_angle, default_step, gsf, keyboard_callback

    # First, see if the program's own keyboard callback handles the key.
    if keyboard_callback and keyboard_callback (key, x, y): return

    # The program's keyboard callback didn't handle it so see if we can.
    fac = 1.1
    if   key == "p" or key == "P":    move_forward (default_step)
    elif key == "l" or key == "L":    move_forward (-default_step)
    elif key == "z" or key == "Z":    move_left (default_step)
    elif key == "x" or key == "X":    move_left (-default_step)
    elif key == "u" or key == "U":    move_up (default_step)
    elif key == "n" or key == "N":    move_up (-default_step)
    elif key == "+":                  default_step  *= fac
    elif key == "-":                  default_step  /= fac
    elif key == "<":                  default_angle *= fac
    elif key == ">":                  default_angle /= fac
    elif key == "a" or key == "A":    rotate_horizontally (default_angle)
    elif key == "s" or key == "S":    rotate_horizontally (-default_angle)
    elif key == "d" or key == "D":    rotate_vertically (-default_angle)
    elif key == "e" or key == "E":    rotate_vertically (default_angle)
    elif key == "r" or key == "R":    reset_viewpoint ()
    elif key == "f" or key == "F":    fly_mode ()
    elif key == "w" or key == "W":    walk_mode ()
    elif key == "v" or key == "V":    view_mode ()
    elif key == "h" or key == "H":    print_keystrokes ()
    elif key == "?":                  print_location ()
    elif key == "5":                  set_sky ("tropical")
    elif key == "q" or key == "Q" or key == "\033":  sys.exit (0)
    glutPostRedisplay ()

def special (key, x, y):
    "Handle the cursor keys."
    global default_angle, default_step
    if   key == GLUT_KEY_UP:     move_forward (default_step)
    elif key == GLUT_KEY_DOWN:   move_forward (-default_step)
    elif key == GLUT_KEY_LEFT:   rotate_horizontally (default_angle)
    elif key == GLUT_KEY_RIGHT:  rotate_horizontally (-default_angle)
    glutPostRedisplay ()

def click (button, state, x, y):
    "When the user clicks the mouse, remember where it was done."
    global lastx, lasty
    lastx = x
    lasty = y
    glutPostRedisplay ()

def mouse (x, y):
    "Move the viewpoint using the mouse."
    global lastx, lasty
    global default_angle, default_step
    if x > lastx:    rotate_horizontally (-default_angle)
    elif x < lastx:  rotate_horizontally (default_angle)
    if y > lasty:    move_forward (-default_step)
    elif y < lasty:  move_forward (default_step)
    lastx = x
    lasty = y
    glutPostRedisplay ()

def get_num (words, idx, default):
    "Parse any number given on a command."
    if len (words) <= idx: return default
    return float (words[idx])

def idle ():
    "When there's nothing else to do..."
    global save_template, pause, gsf, host
    global idle_callback, keyboard_callback, command_callback, cmd_table

    if idle_callback: idle_callback ()
    if waiting():
        glutPostRedisplay ()
        return
    c = command_listener ()

    # Handle the commands that take no arguments and are guaranteed to be
    # available.
    if c ==  "help":
        print_keystrokes ()
        return
    elif c ==  "quit":
        sys.exit (0)

    # See if this can be handled by the program's command callback.
    if command_callback and c != "" and command_callback (c):
        if pause > 0: wait_for (pause)
        glutPostRedisplay ()
        return

    # The other commands all take an argument, so split the line up into
    # whitespace-delimited words and pull out the command.
    words = c.split ()
    if len (words) < 1:
        return   # ignore empty commands
    c = words[0]

    if keyboard_callback:
        if c in cmd_table:
            k = cmd_table[c]
            if keyboard_callback (k, -1, -1):
                if pause > 0: wait_for (pause)
                glutPostRedisplay ()
                return

    if c == "viewpoint":
        # We sometimes receive pairs of viewpoint commands in the same packet
        # (I know not yet why), so reject any commands that don't have exactly
        # the number of parameters we expect.
        if len (words) == 10 or len (words) == 11:
            CX = float (words[1])
            CY = float (words[2])
            CZ = float (words[3])
            VX = float (words[4])
            VY = float (words[5])
            VZ = float (words[6])
            UX = float (words[7])
            UY = float (words[8])
            UZ = float (words[9])
            set_viewpoint (CX, CY, CZ, VX, VY, VZ, UX, UY, UZ)
    elif c ==  "move_forward":
        v = get_num (words, 1, default_step)
        move_forward (v)
    elif c ==  "move_backward":
        v = get_num (words, 1, default_step)
        move_forward (-v)
    elif c ==  "move_left":
        v = get_num (words, 1, default_step)
        move_left (v)
    elif c ==  "move_right":
        v = get_num (words, 1, default_step)
        move_left (-v)
    elif c ==  "move_up":
        v = get_num (words, 1, default_step)
        move_up (v)
    elif c ==  "move_up":
        v = get_num (words, 1, default_step)
        move_up (-v)
    elif c ==  "turn_left":
        v = get_num (words, 1, default_ang)
        rotate_horizontally (-v)
    elif c ==  "turn_right":
        v = get_num (words, 1, default_ang)
        rotate_horizontally (v)
    elif c ==  "turn_down":
        v = get_num (words, 1, default_ang)
        rotate_vertically (-v)
    elif c ==  "turn_up":
        v = get_num (words, 1, default_ang)
        rotate_vertically (v)
    elif c == "reset_viewpoint":
        reset_viewpoint ()
    elif c == "fly_mode":
        fly_mode ()
    elif c == "walk_mode":
        walk_mode ()
    elif c == "view_mode":
        view_mode ()
    elif c == "play_audio" and host != "right-server":
        if os.path.isfile(words[1]):
            os.system ("mpg123 -q " + words[1] + " &")
        else:
            say ("File %s doesn't exist!" % words[1])
    elif c == "volume" and host == "right-server":
        v = int( get_num (words, 1, 100))
        os.system ("amixer -q sset Master %d%%" % v)
    elif c == "louder" and host == "right-server":
        os.system ("amixer -q sset Master 5%+")
    elif c == "quieter" and host == "right-server":
        os.system ("amixer -q sset Master 5%-")
    elif c == "save_frame":
        save_frame_number = int (words[1])
    elif c == "save_template":
        save_template = words[1]
    elif c == "pause":
        pause = float (words[1])
    elif c == "save":
        if len (words) <= 1:
            save ()
        elif words[1] == "on":
            set_saving_mode (True)
        elif words[1] == "off":
            set_saving_mode (False)
    elif c == "seed":
        seed = int (words[1])
    else:
        return

    if pause > 0: wait_for (pause)
    glutPostRedisplay ()

#-------------------------------------------------------------------------------
# Routines to support running OpenGL models in the NIL.
#-------------------------------------------------------------------------------
all_gtms = {
    "left-server":  [1, 0, 0, 0,  0, 1, 0, 0,   0, 0, 1, 0,  0.08, 0, 0, 1],
    "right-server": [1, 0, 0, 0,  0, 1, 0, 0,   0, 0, 1, 0,     0, 0, 0, 1],
    "cseenil1":     [0, 0,-1, 0,  0, 1, 0, 0,   1, 0, 0, 0,     0, 0, 0, 1],
    "cseenil3":     [0, 0, 1, 0,  0, 1, 0, 0,  -1, 0, 0, 0,     0, 0, 0, 1]
    }
gtm = all_gtms["right-server"]    # right eye view by default
gsf = 1
host = "<unknown>"
nil_args = []

def init (args):
    "Initialize a program that is running in the NIL."
    global all_gtmss, gtm, host, nil_args, pause

    # Process the command line.  Set up the various qualifiers that we accept.
    parser = argparse.ArgumentParser ()
    parser.add_argument ("-port", type=int, default=6666,
          help="TCP port on the NIL controller from which commands are read")
    parser.add_argument ("-controller", default="nil-command",
          help="name of the NIL controller from which commands are read")
    parser.add_argument ("-window", action="store_true",
          help="display the rendered output in a window")
    parser.add_argument ("-width", "-W", type=int, default=640,
          help="width of rendered frames when drawn in a window")
    parser.add_argument ("-height", "-H", type=int, default=480,
          help="height of rendered frames when drawn in a window")
    parser.add_argument ("-save", action="store_true",
          help="save rendered frames to files")
    parser.add_argument ("-pause", type=float, default=0.04,
          help="pause in seconds between frames")
    parser.add_argument ("-X", type=int,
          help="x-position of window when not operating full-screen")
    parser.add_argument ("-Y", type=int,
          help="y-position of window when not operating full-screen")

    # A program is invoked with "-net" or "-play" (with a script) or nothing.
    group = parser.add_mutually_exclusive_group()
    group.add_argument ("-net", "-nil", action="store_true",
          help="take commands from the NIL controller")
    group.add_argument ("-play", help="take commands from the specified file")
    nil_args = parser.parse_args (args[1:])

    # Remember the duration of any pause.
    pause = nil_args.pause

    # Determine whether we are running on a NIL machine and set up the
    # transformation relative to the right eye.
    host = socket.gethostname ()
    if all_gtms.has_key (host): gtm = all_gtms[host]

    # Set up the display, depending on which machine we are on and whether or
    # not we have been told to run in a window rather than full-screen.
    game_mode = {
        "vulcan": "1280x768:32@75",
        "neptune.local": "1440x900",
        "cseeneptune.essex.ac.uk": "1440x900",
        "clarkia": "1920x1200:32@60",
        "cseenil1": "1280x1024:32@60",
        "cseenil2": "1280x1024:32@60",
    }
    if nil_args.window:
        glutInitWindowSize (nil_args.width, nil_args.height)
        if nil_args.X and nil_args.Y:
            glutInitWindowPosition (nil_args.X, nil_args.Y)
        glutCreateWindow (sys.argv[0])
        width = nil_args.width
    else:
        if host in game_mode:
            glutGameModeString (game_mode[host])
            glutEnterGameMode ()
            width = glutGameModeGet (GLUT_GAME_MODE_WIDTH)
        else:
            glutCreateWindow (sys.argv[0])
           
            width = glutGet (GLUT_WINDOW_WIDTH)

    # Wait for the framebuffer to become available before continuing.
    have_waited = False
    while True:
        if glCheckFramebufferStatus (GL_FRAMEBUFFER): break
        print "Z",
        have_waited = True
        time.sleep(1)
    if have_waited: print

    # Set up saving frames if the command-line qualifier was present.
    if nil_args.save: set_saving_mode (True)

    # Do miscellaneous OpenGL setting up.
    glutSetCursor (GLUT_CURSOR_NONE)
    w = width // 400   # for 10-pixel-wide lines on main NIL display
    if w < 1: w  = 1
    glLineWidth (w)

def command_listener_begin ():
    """Set things up to read commands from a file or the network, depending on
    the command line."""
    global read_list, command_stream, nil_args, host

    if nil_args.play:
        command_stream = open (nil_args.play)
        print >>sys.stderr,  "[reading from file %s]" % nil_args.play
    elif nil_args.net:
        hn, port = nil_args.controller, nil_args.port
        command_stream = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
        command_stream.connect ((hn, port))
        command_stream.setblocking (0)
        read_list = [command_stream]
        print >>sys.stderr,  "\r[%s: connected to %s on port %d]\r" % \
          (host, hn, port)
    else:
        print >>sys.stderr, "[taking commands from your keyboard and mouse]"
        print_keystrokes (sys.stderr)

def command_listener ():
    """Receive a command, if we're running a script or taking commands over
    the network."""
    global read_list, command_stream, nil_args

    if nil_args.play:
        line = command_stream.readline()
        if line:
            data = line.rstrip()
            return data
        else:
            command_listener_end ()
            nil_args.play = False
    elif nil_args.net:
        try:
            data = command_stream.recv(4096)
        except socket.error, e:
            err = e.args[0]
            if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                return ""
        if data:
            if data == "quit":
                print "\r[Exiting]\r"
                command_listener_end ()
                exit (0)
        return data
    return ""

def command_listener_end ():
    "Close off any input stream we're reading commands from."
    global read_list, command_stream, nil_args

    if nil_args.play:
        command_stream.close ()
    elif nil_args.net:
        for s in read_list:
            s.close ()

def load_keys (fn):
    "Load a keyboard map from a file.  Lines have the format 'k k...: cmd'."
    global key_table, cmd_table
    # Open the file and read it a line at a time.
    found = False
    for dir in ["", "./", "/Users/alien/work/models/clients/",
                "/home/alien/",
                "./"]:
        ffn = dir + fn
        if os.path.exists (ffn):
            found = True
            break
    if not found:
        print >>sys.stderr, "Keyboard mapping file %s not found." % fn
        return

    f = open (ffn)
    for line in f:
        # Strip leading and trailing whitespace, ignore blanks and comments.
        line = line.strip ()
        if len (line) < 1: continue
        if line[0] == "#": continue
        # Pull out the keys and corresponding command, storing the result.
        k, cmd = line.split (":")
        cmd = cmd.strip ()
        keys = k.split ()
        for k in keys:
            cmd_table[cmd] = k
            key_table[k] = cmd
    f.close()

#-------------------------------------------------------------------------------
# Convenience routines for loading textures and an all-encompassing skybox.
#-------------------------------------------------------------------------------
def load_texture (path, mipmap=False):
    "Given an image in path, load it and convert it into an OpenGL texture."
    glClearColor (0.3,0.3,0.3,1.0)
    glEnable (GL_DEPTH_TEST)

    image = Image.open(path)
    (width, height) = image.size[0:2]
    if image.mode == "RGB":
        pixel_data = image.tobytes ()
    elif image.mode == "RGBA":
        pixel_data = image.tobytes ("raw", "RGB", 0, -1)
    elif image.mode == "L":
        pixel_data = image.convert("RGBA").tobytes ("raw", "RGB")
    else:
        print >>sys.stderr, "Unsupported image mode", image.mode, "for", path
        sys.exit (1)
    texture = glGenTextures (1)
    glPixelStorei (GL_UNPACK_ALIGNMENT, 1)
    glBindTexture (GL_TEXTURE_2D, texture)
    if mipmap:
        glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_WRAP_R, GL_REPEAT)
        glTexParameterf (GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER,
                         GL_LINEAR_MIPMAP_LINEAR)
        glTexParameterf (GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER,
                         GL_LINEAR)
        gluBuild2DMipmaps(GL_TEXTURE_2D, GL_RGBA, width, height, GL_RGB,
                     GL_UNSIGNED_BYTE, pixel_data)
    else:
        glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_WRAP_R, GL_REPEAT)
        glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, width, height, 0, GL_RGB,
                     GL_UNSIGNED_BYTE, pixel_data)
    glTexEnvf(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE)
    return texture

available_skyboxes = ["mono", "default", "cloudy", "cloudrays",
                      "stormy", "tropical", "sunset", "moonlit"]
skyboxsize = 1000        # half-size of any skybox that we draw
skybox = []              # the textures, when loaded

def set_sky (box="default"):
    "Set the skybox to use."
    global sky, available_skyboxes
    for b in available_skyboxes:
        if b == box:
            sky = box
            return
    print >>sys.stderr, "Skybox called", box, "is not supported."
    box = "default"

def get_sky ():
    "Return the current skybox."
    global sky
    return sky

def draw_sky (type="default", dir=["./skybox",
                                   "/Users/alien/work/models/skybox"]):
    "Draw an all-encompassing box with a sky texture mapped onto it."
    global skybox, skyboxsize
    if len (skybox) == 0:
        # Load the textures for the enclosing sky box.
        for f in ['front', 'left', 'back', 'right', 'top', 'bottom']:
            fn = "sky_%s_%s.jpg" % (type, f)
            for d in dir:
                ffn = os.path.join (d, fn)
                if os.path.exists (ffn):
                    tim = load_texture (ffn)
                    skybox += [tim]
                    break
        if len(skybox) == 0:
            print >>sys.stderr, "Alas, no skybox textures could be found."
            return

    d = skyboxsize
    glPushMatrix ()
    glPushAttrib (GL_ENABLE_BIT)
    glEnable (GL_TEXTURE_2D)
    glDisable (GL_DEPTH_TEST)
    glDisable (GL_LIGHTING)
    glDisable (GL_BLEND)
    glColor4f (1.0, 1.0, 1.0, 1.0)

    # One thing to remember is that OpenGL measures its coordinates from the
    # LOWER left coordinate of the image; hence, the y-values in the calls to
    # glTexCoord2f are the converse from what the geometry suggests.  This
    # avoids us having to remember to store images upside down for use in
    # texture maps.  All of the following are ordered anticlockwise from the
    # bottom left.
    glBindTexture (GL_TEXTURE_2D, skybox[0])  # front
    glBegin (GL_QUADS)
    glTexCoord2f (0, 1); glVertex3f (-d, -d, -d)
    glTexCoord2f (1, 1); glVertex3f ( d, -d, -d)
    glTexCoord2f (1, 0); glVertex3f ( d,  d, -d)
    glTexCoord2f (0, 0); glVertex3f (-d,  d, -d)
    glEnd ()

    glBindTexture (GL_TEXTURE_2D, skybox[3])  # left
    glBegin (GL_QUADS)
    glTexCoord2f (0, 1); glVertex3f (-d, -d,  d)
    glTexCoord2f (1, 1); glVertex3f (-d, -d, -d)
    glTexCoord2f (1, 0); glVertex3f (-d,  d, -d)
    glTexCoord2f (0, 0); glVertex3f (-d,  d,  d)
    glEnd ()

    glBindTexture (GL_TEXTURE_2D, skybox[2])  # back
    glBegin (GL_QUADS)
    glTexCoord2f (0, 1); glVertex3f ( d, -d,  d)
    glTexCoord2f (1, 1); glVertex3f (-d, -d,  d)
    glTexCoord2f (1, 0); glVertex3f (-d,  d,  d)
    glTexCoord2f (0, 0); glVertex3f ( d,  d,  d)
    glEnd ()

    glBindTexture (GL_TEXTURE_2D, skybox[1])  # right
    glBegin (GL_QUADS)
    glTexCoord2f (0, 1); glVertex3f ( d, -d, -d)
    glTexCoord2f (1, 1); glVertex3f ( d, -d,  d)
    glTexCoord2f (1, 0); glVertex3f ( d,  d,  d)
    glTexCoord2f (0, 0); glVertex3f ( d,  d, -d)
    glEnd ()

    glBindTexture (GL_TEXTURE_2D, skybox[4])  # top
    glBegin (GL_QUADS)
    glTexCoord2f (1, 1); glVertex3f (-d,  d, -d)
    glTexCoord2f (0, 1); glVertex3f (-d,  d,  d)
    glTexCoord2f (0, 0); glVertex3f ( d,  d,  d)
    glTexCoord2f (1, 0); glVertex3f ( d,  d, -d)
    glEnd ()

    glBindTexture (GL_TEXTURE_2D, skybox[5])  # bottom
    glBegin (GL_QUADS)
    glTexCoord2f (0, 0); glVertex3f ( -d, -d, -d)
    glTexCoord2f (0, 1); glVertex3f ( -d, -d,  d)
    glTexCoord2f (1, 1); glVertex3f (  d, -d,  d)
    glTexCoord2f (1, 0); glVertex3f (  d, -d, -d)
    glEnd ()

    glPopAttrib ()
    glPopMatrix ()

#-------------------------------------------------------------------------------
# Miscellaneous routines.
#-------------------------------------------------------------------------------
def rad (a):
    "Convert degrees to radians."
    return a * pi / 180.0

def deg (a):
    "Convert radians to degrees."
    return a * 180.0 / pi

def dcos (a):
    "Cosine of an angle in degrees."
    return cos (rad (a))

def dsin (a):
    "Sine of an angle in degrees."
    return sin (rad (a))

def find_in_path (prog):
    "Return the absolute pathname of a program which is in the search path."
    # First, split the PATH variable into a list of directories, then find
    # the first program from our list that is in the path.
    path = string.split(os.environ['PATH'], os.pathsep)
    for p in path:
        fp = os.path.join(p, prog)
        if os.path.exists(fp): return os.path.abspath(fp)
    return None

def say (text, async=False):
    "Output some text via the system's speech synthesizer"
    if host == "left-server": return  # no sound output on this computer
    if find_in_path ('say'):
        if async: os.system ('say ' + text + '&')
        else: os.system ('say ' + text)
    elif find_in_path ('flite'):
        os.system ('flite " ' + text + '" &> /dev/null')
    else:
        print >>sys.stderr, text

def wait_for (delay):
    """Set up a busy-wait until <when>.  This is used principally to allow
    animations to play."""
    global wait_until
    wait_until = time.time () + delay

def waiting ():
    "Say whether we are currently busy-waiting."
    global wait_until

    if time.time () < wait_until:
        return True
    return False

#-------------------------------------------------------------------------------
# Graphics routines.
#-------------------------------------------------------------------------------

def vector_product (xyz1, xyz2):
    "Calculate the vector product of two vectors"
    x = xyz1[1] * xyz2[2] - xyz1[2] * xyz2[1]
    y = xyz1[2] * xyz2[0] - xyz1[0] * xyz2[2]
    z = xyz1[0] * xyz2[1] - xyz1[1] * xyz2[0]
    return (x, y, z)

def veclen (xyz):
    "Find the length of a vector"
    return sqrt (xyz[0]**2 + xyz[1]**2 + xyz[2]**2)

def normalize (xyz):
    "Normalize a vector"
    size = veclen (xyz)
    return (xyz[0]/size,  xyz[1]/size, xyz[2]/size)

def cylinder (xyz1, xyz2, r, sides=8, a1=0, a2=360, closed=True):
    """Output the definition of a cylinder of radius r with ends at
    xyz1 and xyz2 between angles a1 and a2 (in degrees).

    Adapted from models.py"""
    # Start by creating a vector from one end to the other.
    vx = xyz1[0] - xyz2[0]
    vy = xyz1[1] - xyz2[1]
    vz = xyz1[2] - xyz2[2]
    axis = [vx, vy, vz]
    r1 = r2 = r   # as the models routine is for a cone

    # Find two perpendicular vectors, p and q, in the plane of the disk and
    # ensure they're normalized.  We get the first by knowing that its
    # scalar product with axis must be zero; there are three cases in case
    # any of the components are zero.
    perp = [vx, vy, vz]
    if vx == 0 and vz == 0: perp[0] += 1
    else:                   perp[1] += 1
    q = vector_product (perp, axis)
    perp = vector_product (axis, q)
    perp = normalize (perp)
    q = normalize (q)

    # Define the polygons that form the sides (and optionally the ends)
    # of the cone.
    ainc = (a2 - a1) / sides * pi / 180.0
    alo = a1 * pi / 180.0
    for i in range (0, sides):
        ang = alo + i * ainc
        nx = cos(ang) * perp[0] + sin(ang) * q[0]
        ny = cos(ang) * perp[1] + sin(ang) * q[1]
        nz = cos(ang) * perp[2] + sin(ang) * q[2]
        n = normalize ((nx, ny, nz))
        p2x = xyz2[0] + r2 * n[0]
        p2y = xyz2[1] + r2 * n[1]
        p2z = xyz2[2] + r2 * n[2]
        p1x = xyz1[0] + r1 * n[0]
        p1y = xyz1[1] + r1 * n[1]
        p1z = xyz1[2] + r1 * n[2]

        ang += ainc
        nx = cos(ang) * perp[0] + sin(ang) * q[0]
        ny = cos(ang) * perp[1] + sin(ang) * q[1]
        nz = cos(ang) * perp[2] + sin(ang) * q[2]
        n = normalize ((nx, ny, nz))
        q1x = xyz1[0] + r1 * n[0]
        q1y = xyz1[1] + r1 * n[1]
        q1z = xyz1[2] + r1 * n[2]
        q2x = xyz2[0] + r2 * n[0]
        q2y = xyz2[1] + r2 * n[1]
        q2z = xyz2[2] + r2 * n[2]

        glBegin (GL_QUADS)
        glVertex3f (p2x, p2y, p2z)
        glVertex3f (p1x, p1y, p1z)
        glVertex3f (q1x, q1y, q1z)
        glVertex3f (q2x, q2y, q2z)
        glEnd ()

        # If the cone is closed, draw part of the end-caps.
        if closed:
            glBegin (GL_POLYGON)
            glVertex3f (xyz1[0], xyz1[1], xyz1[2])
            glVertex3f (p1x, p1y, p1z)
            glVertex3f (q1x, q1y, q1z)
            glEnd ()
            
            glBegin (GL_POLYGON)
            glVertex3f (xyz2[0], xyz2[1], xyz2[2])
            glVertex3f (p2x, p2y, p2z)
            glVertex3f (q2x, q2y, q2z)
            glEnd ()

#-------------------------------------------------------------------------------
# A version routine that returns the timestamp maintained by Emacs.
#-------------------------------------------------------------------------------
def version ():
    "Return the version of this library."
    return timestamp[13:-1]

#-------------------------------------------------------------------------------
# Load the default keymap.
#-------------------------------------------------------------------------------
load_keys ("nil.kbd")

timestamp = "Time-stamp: <2018-07-01 17:56:06 Adrian F Clark (alien@essex.ac.uk)>"
# Local Variables:
# time-stamp-line-limit: -10
# End:
#-------------------------------------------------------------------------------
# End of nilgl.py
#-------------------------------------------------------------------------------
