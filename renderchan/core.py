__author__ = 'Konstantin Dmitriev'

import sys
from renderchan.file import RenderChanFile
from renderchan.project import RenderChanProjectManager
from renderchan.module import RenderChanModuleManager
from renderchan.utils import mkdirs
from puliclient import Task, Graph
import os, time

class RenderChan():
    def __init__(self):

        self.puliServer = ""
        self.puliPort = 8004

        print "RenderChan initialized."
        self.projects = RenderChanProjectManager()
        self.modules = RenderChanModuleManager()
        self.modules.loadAll()

        self.loadedFiles = {}

        self.graph = Graph( 'RenderChan graph', poolName="default" )

    def setHost(self, host):
        self.puliServer=host

    def setPort(self, port):
        self.puliPort=port

    def submit(self, taskfile, useDispatcher=True):

        """

        :type taskfile: RenderChanFile
        """

        self.parseRenderDependency(taskfile)

        # Finally submit the graph to Puli

        if self.puliServer=="":
            server="127.0.0.1"
            # TODO: If no server address given, then try to run our own dispatcher
            # ...
        else:
            server=self.puliServer

        if useDispatcher:
            # Submit to dispatcher host
            self.graph.submit(server, self.puliPort)
        else:
            # Local rendering
            self.graph.execute()

    def parseRenderDependency(self, taskfile):
        """

        :type taskfile: RenderChanFile
        """
        isDirty = False
        if not os.path.exists(taskfile.getRenderPath()+".done"):
            # If no rendering exists, then obviously rendering is required
            isDirty = True
            compareTime = None
        else:
            # Otherwise we have to check against the time of the last rendering
            compareTime = os.path.getmtime(taskfile.getRenderPath()+".done")

        # Get "dirty" status for the target file and all dependent tasks, submitted as dependencies
        (isDirtyValue,tasklist, maxTime)=self.parseDirectDependency(taskfile, compareTime, [])

        if isDirtyValue:
            isDirty = True

        # If rendering is requested
        if isDirty:

            # Puli part here

            name = taskfile.getPath()
            runner = "renderchan.puli.RenderChanRunner"
            decomposer = "renderchan.puli.RenderChanDecomposer"

            params = taskfile.getParams()
            # Max time is a
            params["maxTime"]=maxTime

            # Make sure we have all directories created
            mkdirs(os.path.dirname(params["profile_output"]))
            mkdirs(os.path.dirname(params["output"]))

            # Add rendering task to the graph
            taskfile.taskRender=self.graph.addNewTask( name="Render: "+name, runner=runner, arguments=params, decomposer=decomposer )


            # Now we will add a task which composes results and places it into valid destination

            # Add rendering task to the graph
            runner = "renderchan.puli.RenderChanPostRunner"
            decomposer = "renderchan.puli.RenderChanPostDecomposer"
            taskfile.taskPost=self.graph.addNewTask( name="Post: "+name, runner=runner, arguments=params, decomposer=decomposer,
                                       maxNbCores=taskfile.module.conf["maxNbCores"] )

            self.graph.addEdges( [(taskfile.taskRender, taskfile.taskPost)] )

            # Add edges for dependent tasks
            for task in tasklist:
                self.graph.addEdges( [(task, taskfile.taskRender)] )

        # Mark this file as already parsed and thus its "dirty" value is known
        taskfile.isDirty=isDirty

        return isDirty


    def parseDirectDependency(self, taskfile, compareTime, tasklist):
        """

        :type taskfile: RenderChanFile
        """

        self.loadedFiles[taskfile.getPath()]=taskfile
        if taskfile.project!=None:
            self.loadedFiles[taskfile.getRenderPath()]=taskfile

        deps = taskfile.getDependencies()

        # maxTime is the maximum of modification times for all direct dependencies.
        # It allows to compare with already rendered pieces and continue rendering
        # if they are rendered AFTER the maxTime.
        #
        # But, if we have at least one INDIRECT dependency (i.e. render task) and it is submitted
        # for rendering, then we can't compare with maxTime (because dependency will be rendered
        # and thus rendering should take place no matter what).
        maxTime = taskfile.getTime()

        taskfile.pending=True  # we need this to avoid circular dependencies

        isDirty=False
        for path in deps:
            if path in self.loadedFiles.keys():
                dependency = self.loadedFiles[path]
                if dependency.pending:
                    # Avoid circular dependencies
                    print "Warning: Circular dependency detected for %s. Skipping." % (path)
                    break
            else:
                dependency = RenderChanFile(path, self.modules, self.projects)

            # Check if this is a rendering dependency
            if path != dependency.getPath():
                # We have a new task to render
                if dependency.isDirty==None:
                    if dependency.module!=None:
                        dep_isDirty = self.parseRenderDependency(dependency)
                    else:
                        raise Exception("No module to render file")
                else:
                    # The dependency was already submitted to graph
                    dep_isDirty = dependency.isDirty

                if dep_isDirty:
                    # Let's return submitted task into tasklist
                    if not dependency.taskPost in tasklist:
                        tasklist.append(dependency.taskPost)
                    # Increase maxTime, because re-rendering of dependency will take place
                    maxTime=time.time()
                    isDirty = True
                else:
                    # If no rendering requested, we still have to check if rendering result
                    # is newer than compareTime

                    #if os.path.exists(dependency.getRenderPath()+".done"):  -- file is obviously exists, because isDirty==0
                    timestamp=os.path.getmtime(dependency.getRenderPath()+".done")

                    if compareTime is None:
                        isDirty = True
                    elif timestamp > compareTime:
                        isDirty = True
                    if timestamp>maxTime:
                        maxTime=timestamp

            else:
                # No, this is an ordinary dependency
                if os.path.exists(dependency.getPath()):
                    (isDirty, dep_tasklist, dep_maxTime) = self.parseDirectDependency(dependency, compareTime,  tasklist) or isDirty
                    if dep_maxTime>maxTime:
                        maxTime=dep_maxTime
                    for task in dep_tasklist:
                        if not task in tasklist:
                            tasklist.append(task)

        if not isDirty:
            timestamp = taskfile.getTime()
            if compareTime is None:
                isDirty = True
            elif timestamp > compareTime:
                isDirty = True

        taskfile.pending=False

        return (isDirty, list(tasklist), maxTime)
