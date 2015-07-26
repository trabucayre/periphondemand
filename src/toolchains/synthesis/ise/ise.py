#! /usr/bin/python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# Name:     ise.py
# Purpose:
# Author:   Fabien Marteau <fabien.marteau@armadeus.com>
# Created:  21/07/2008
# ----------------------------------------------------------------------------
#  Copyright (2008)  Armadeus Systems
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# ----------------------------------------------------------------------------
""" Manage ISE toolchain """

import time
import datetime

from periphondemand.bin.define import SYNTHESISPATH
from periphondemand.bin.define import OBJSPATH
from periphondemand.bin.define import BINARYPROJECTPATH
from periphondemand.bin.define import UCFEXT
from periphondemand.bin.define import VHDLEXT
from periphondemand.bin.define import TCLEXT
from periphondemand.bin.define import COLOR_SHELL
from periphondemand.bin.define import COLOR_END
from periphondemand.bin.define import BINARY_PREFIX
from periphondemand.bin.define import XILINX_BITSTREAM_SUFFIX
from periphondemand.bin.define import XILINX_BINARY_SUFFIX
from periphondemand.bin.define import ONETAB

from periphondemand.bin.utils.settings import Settings
from periphondemand.bin.utils.poderror import PodError
from periphondemand.bin.utils.display import Display
from periphondemand.bin.utils import wrappersystem as sy

from periphondemand.bin.core.component import Component
from periphondemand.bin.core.port import Port
from periphondemand.bin.core.interface import Interface
from periphondemand.bin.core.hdl_file import HdlFile

SETTINGS = Settings()
DISPLAY = Display()


def generatelibraryconstraints(self):
    """ Adds constraints specified by a component, such as placement for a PLL,
        multiplier, etc. or clock informations about PLL output signals
    """
    out = "# components constraints \n"
    for instance in self.project.instances:
        for constraint in instance.constraints:
            instanceName = instance.instancename
            attrValName = str(constraint.get_attr_value("name"))
            if constraint.get_attr_value("type") == "clk":
                attrValNameUnder = attrValName.replace('/', '_')
                out += "NET \"" + instanceName + "/" + attrValName +\
                       "\" TNM_NET = " + instanceName + "/" +\
                       attrValName + ";\n"
                out += "TIMESPEC TS_" + instanceName + "_" +\
                       attrValNameUnder + " = PERIOD \"" + instanceName +\
                       "/" + attrValName + "\""
                out += " %g" %\
                    (1000 /
                        float(constraint.get_attr_value("frequency"))) +\
                    " ns HIGH 50%;\n"
            elif constraint.get_attr_value("type") == "placement":
                out += "INST \"" + instanceName + "/" +\
                    attrValName + "\" LOC=" +\
                    constraint.get_attr_value("loc") + ";\n"
            else:
                raise PodError("component " + instance.name +
                               " has an unknown type " +
                               constraint.get_attr_value("type"), 0)
    return out


def generate_pinout(self, filename=None):
    """ Generate the constraint file .ucf for xilinx fpga
    """
    if filename is None:
        filename = SETTINGS.projectpath + SYNTHESISPATH + "/" + \
            SETTINGS.active_project.name + UCFEXT

    self.project = SETTINGS.active_project
    out = "# Constraint file, automaticaly generated by pod \n"
    for interface in self.project.platform.interfaces:
        for port in interface.ports:
            if port.force_defined():
                out = out + 'NET "force_' + str(port.name)
                out = out + '" LOC="' + str(port.position)\
                          + '" | IOSTANDARD=' + str(port.standard)
                if port.drive is not None:
                    out = out + " | DRIVE=" + str(port.drive)
                out = out + r'; # ' + str(port.name) + '\n'
            elif port.pins != []:
                pin = port.pins
                # Platform ports are all 1-sized, raise error if not
                if len(pin) != 1:
                    raise PodError("Platform port " + port.name +
                                   " has size different of 1", 0)
                pin = pin[0]
                # Only one connection per platform pin can be branched.
                # If several connections found, only first is used
                if pin.connections != []:
                    # XXX use getConnectedPinList
                    connect = pin.connections
                    if len(connect) > 1:
                        same_connections_ports = []
                        DISPLAY.msg("severals pin connected to " +
                                    port.name, 2)
                        for connection in connect:
                            DISPLAY.msg("      -> " +
                                        connection["instance_dest"] + "." +
                                        connection["interface_dest"] + "." +
                                        connection["port_dest"] + "." +
                                        connection["pin_dest"])
                            same_connections_ports.append(
                                connection["instance_dest"] + "_" +
                                connection["port_dest"])

                        same_connections_ports.sort()
                        for connection in connect:
                            if connection["instance_dest"] +\
                                    "_" + connection["port_dest"] ==\
                                    same_connections_ports[0]:
                                        connect = connection
                        DISPLAY.msg("Connection name: " +
                                    connect["instance_dest"] + "." +
                                    connect["interface_dest"] + "." +
                                    connect["port_dest"] + "." +
                                    connect["pin_dest"], 3)
                    else:
                        connect = connect[0]

                    instancedest =\
                        self.project.get_instance(connect["instance_dest"])
                    interfacedest =\
                        instancedest.get_interface(connect["interface_dest"])
                    portdest = interfacedest.get_port(connect["port_dest"])

                    out = out + 'NET "' +\
                        connect["instance_dest"] + "_" + connect["port_dest"]
                    if self.project.get_instance(
                            connect["instance_dest"]).get_interface(
                                connect["interface_dest"]).get_port(
                                    connect["port_dest"]).size != "1":
                        if portdest.is_fully_connected():
                            out = out + "<" + connect["pin_dest"] + ">"
                        else:
                            out = out + "_pin" + connect["pin_dest"]
                    out = out + '" LOC="' + str(port.position) + '"'
                    if portdest.port_option is not None:
                        out = out + ' | ' + str(portdest.port_option)
                    elif port.port_option is not None:
                        out = out + ' | ' + str(port.port_option)
                    if portdest.standard is not None:
                        out = out + " | IOSTANDARD=" +\
                            str(portdest.standard)
                    else:
                        out = out + " | IOSTANDARD=" + str(port.standard)
                    if portdest.drive is not None:
                        out = out + " | DRIVE=" + str(portdest.drive)
                    elif port.drive is not None:
                        out = out + " | DRIVE=" + str(port.drive)
                    out = out + r'; # ' + str(port.name) + '\n'

                    # if port as frequency parameters, it's a clock.
                    # then had xilinx clock constraint
                    try:
                        frequency = port.frequency
                        out = out + "NET \"" +\
                            connect["instance_dest"] +\
                            "_" + connect["port_dest"] +\
                            "\" TNM_NET = \"" +\
                            connect["instance_dest"] +\
                            "_" + connect["port_dest"] +\
                            "\";\n"
                        out = out + "TIMESPEC \"TS_" +\
                            connect["instance_dest"] +\
                            "_" + connect["port_dest"] +\
                            "\" = PERIOD \"" +\
                            connect["instance_dest"] +\
                            "_" + connect["port_dest"] +\
                            "\" " +\
                            "%g" % ((1000 / float(frequency))) +\
                            " ns HIGH 50 %;\n"
                    except:
                        pass

    out = out + generatelibraryconstraints(self)
    out = out + "#end\n"
    try:
        afile = open(filename, "w")
    except IOError, error:
        raise PodError(str(error), 0)
    afile.write(out)
    afile.close()
    DISPLAY.msg("Constraint file generated with name : " + filename)
    return filename


def generate_tcl(self, filename=None):
    """ generate tcl script for ise
    """
    if filename is None:
        filename = SETTINGS.active_project.name + TCLEXT
    tclfile = open(SETTINGS.projectpath + SYNTHESISPATH + "/" + filename, "w")
    tclfile.write("# TCL script automaticaly generated by POD\n")
    tclfile.write("cd .." + OBJSPATH + "\n")
    # create project
    tclfile.write("project new " + SETTINGS.active_project.name + "\n")

    # Configuration
    tclfile.write("# configure platform params\n")
    platform = SETTINGS.active_project.platform
    tclfile.write("project set family " + platform.family + "\n")
    tclfile.write("project set device " + platform.device + "\n")
    tclfile.write("project set package " + platform.package + "\n")
    tclfile.write("project set speed " + platform.speed + "\n")
    tclfile.write("project set {Preferred Language} VHDL\n")
    tclfile.write('project set "Create Binary Configuration File" TRUE\n')

    # Source files
    tclfile.write("## add components sources file\n")
    tclfile.write("# add top level sources file\n")
    tclfile.write("xfile add .." + SYNTHESISPATH + "/top_" +
                  SETTINGS.active_project.name + VHDLEXT + "\n")

    for directory in sy.list_dir(SETTINGS.projectpath + SYNTHESISPATH):
        for afile in sy.list_files(SETTINGS.projectpath +
                                   SYNTHESISPATH +
                                   "/" + directory):
            tclfile.write("xfile add .." + SYNTHESISPATH + "/" +
                          directory + "/" + afile + "\n")

    # Constraints files
    tclfile.write("# add constraint file\n")
    tclfile.write("xfile add .." + SYNTHESISPATH + "/" +
                  SETTINGS.active_project.name + UCFEXT + " \n")
    tclfile.write("set constraints_file .." + SYNTHESISPATH + "/" +
                  SETTINGS.active_project.name + UCFEXT + " \n")
    tclfile.write('project set "Load Physical Constraints File" "Default" ' +
                  '-process "Analyze Power Distribution (XPower Analyzer)"\n')
    tclfile.write('project set "Load Physical Constraints File" "Default" ' +
                  '-process "Generate Text Power Report"\n')
    tclfile.write('project set "Target UCF File Name" "" ' +
                  '-process "Back-annotate Pin Locations"\n')
    tclfile.write('project set "Ignore User Timing Constraints" "false" ' +
                  '-process "Map"\n')
    # Run synthesis
    tclfile.write('process run "Synthesize"\n')
    tclfile.write('process run "Translate"\n')
    tclfile.write('process run "Map"\n')
    tclfile.write('process run "Place & Route"\n')
    tclfile.write('process run "Generate Programming File"\n')

    # Run post synthesis model generation
    tclfile.write('process run "Generate Post-Synthesis Simulation Model"\n')
    #    tclfile.write('cp netgen/synthesis/top_' +
    #                    SETTINGS.active_project.name + \
    #        '_synthesis.vhd ../simulation/\n')
    # Run post place and route model generation
    tclfile.write('process run ' +
                  '"Generate Post-Place & Route Simulation Model"\n')
    tclfile.write('process run "Implement Design" -force rerun_all\n')
    tclfile.write('project close\n')

    DISPLAY.msg("TCL script generated with name : " +
                SETTINGS.active_project.name + TCLEXT)
    return SETTINGS.active_project.name + TCLEXT


def generate_bitstream(self, commandname, scriptname):
    """ generate the bitstream """
    pwd = sy.pwd()
    sy.del_all(SETTINGS.projectpath + OBJSPATH)
    sy.chdir(SETTINGS.projectpath + SYNTHESISPATH)
    commandname = commandname + " < "

    for line in sy.launch_as_shell(commandname, scriptname):
        if SETTINGS.color() == 1:
            print COLOR_SHELL + line + COLOR_END,
        else:
            print "SHELL>" + line,
    try:
        sy.cp_file(SETTINGS.projectpath + OBJSPATH + "/" +
                   BINARY_PREFIX + SETTINGS.active_project.name +
                   XILINX_BITSTREAM_SUFFIX,
                   SETTINGS.projectpath + BINARYPROJECTPATH + "/")
        sy.cp_file(SETTINGS.projectpath + OBJSPATH + "/" +
                   BINARY_PREFIX + SETTINGS.active_project.name +
                   XILINX_BINARY_SUFFIX,
                   SETTINGS.projectpath + BINARYPROJECTPATH + "/")
    except IOError:
        raise PodError("Can't copy bitstream")
    sy.chdir(pwd)
