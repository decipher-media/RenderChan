

__author__ = 'scribblemaniac'

from renderchan.module import RenderChanModule
from renderchan.utils import which
import subprocess
import gzip
import os
import re
import random

class RenderChanInkscapeModule(RenderChanModule):
    def __init__(self):
        RenderChanModule.__init__(self)
        if os.name == 'nt':
            self.conf['binary']=os.path.join(os.path.dirname(__file__),"..\\..\\..\\inkscape\\inkscape.exe")
        else:
            self.conf['binary']="inkscape"
        self.conf["packetSize"]=0

    def getInputFormats(self):
        return ["svg", "svgz", "ai", "cdr", "vsd"]

    def getOutputFormats(self):
        return ["png", "ps", "eps", "pdf", "emf", "wmf"]

    def analyze(self, filename):
        info={"dependencies":[]}

        if filename.endswith(".svgz"):
            f=gzip.open(filename)
        else:
            f=open(filename)

        linkPattern = re.compile(".*sodipodi:absref=\"(.*?)\".*")
        for line in f.readlines():
            pat=linkPattern.search(line)
            if pat:
                info["dependencies"].append(pat.group(1).strip())
        f.close

        return info

    def checkRequirements(self):
        if which(self.conf['binary']) == None:
            self.active=False
            print "Module warning (%s): Cannot find '%s' executable." % (self.getName(), self.conf["binary"])
            print "    Please install inkscape package."
        else:
            self.active=True
        return self.active

    def render(self, filename, outputPath, startFrame, endFrame, format, updateCompletion, extraParams={}):

        comp = 0.0
        updateCompletion(comp)

        commandline=[self.conf['binary'], "--file=" + filename, "--without-gui", "--export-width=" + extraParams["width"], "--export-height=" + extraParams["height"], "--export-%s=%s" % (format, outputPath)]
        subprocess.check_call(commandline)

        updateCompletion(1.0)