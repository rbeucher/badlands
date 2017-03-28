import time
import numpy as np
import mpi4py.MPI as mpi

from scipy.spatial import cKDTree
from pyBadlands import (diffLinear, flowNetwork, buildMesh,
                        checkPoints, buildFlux, xmlParser)

# Profiling support
import cProfile
import os
import pstats
import StringIO


class Model(object):
    """State object for the pyBadlands model."""

    def __init__(self):
        """
        Constructor.
        """

        # Simulation state
        self.tNow = 0.
        self.outputStep = 0
        self.disp = None
        self.applyDisp = False
        self.simStarted = False

        self._rank = mpi.COMM_WORLD.rank
        self._size = mpi.COMM_WORLD.size
        self._comm = mpi.COMM_WORLD

    def load_xml(self, filename, verbose=False):
        """
        Load an XML configuration file.

        Parameters
        ----------
        filename : string
            Path to the XML file to load.

        verbose : bool
            When True, output additional debug information.
        """

        # Only the first node should create a unique output dir
        self.input = xmlParser.xmlParser(filename, makeUniqueOutputDir=(self._rank == 0))
        self.tNow = self.input.tStart

        # Sync the chosen output dir to all nodes
        self.input.outDir = self._comm.bcast(self.input.outDir, root=0)

        # Seed the random number generator consistently on all nodes
        seed = None
        if self._rank == 0:
            # limit to max uint32
            seed = np.random.mtrand.RandomState().tomaxint() % 0xFFFFFFFF
        seed = self._comm.bcast(seed, root=0)
        np.random.seed(seed)

        # If there's no demfile specified, we assume that it will be loaded
        # later using build_mesh
        if self.input.demfile:
            self.build_mesh(self.input.demfile, verbose)

    def build_mesh(self, filename, verbose):
        # Construct Badlands mesh and grid to run simulation
        self.recGrid, self.FVmesh, self.force, self.tMesh, self.lGIDs, self.fixIDs, self.inIDs, parentIDs, \
            self.inGIDs, self.totPts, self.elevation, self.cumdiff, self.cumflex, self.strata, self.mapero, \
            self.tinFlex, self.flex, self.straTIN = buildMesh.construct_mesh(self.input, filename, verbose)

        # Define hillslope parameters
        self.rain = np.zeros(self.totPts, dtype=float)
        self.hillslope = diffLinear()
        self.hillslope.CDaerial = self.input.CDa
        self.hillslope.CDmarine = self.input.CDm
        self.hillslope.CDriver = self.input.CDr

        # Define flow parameters
        self.flow = flowNetwork(self.input)

        if self.input.erolays is None:
            self.flow.erodibility = np.full(self.totPts, self.input.SPLero)
        else:
            self.flow.erodibility = self.mapero.erodibility
        self.flow.mindt = self.input.minDT
        self.flow.xycoords = self.FVmesh.node_coords[:,:2]
        self.flow.spl = self.input.spl
        self.flow.depo = self.input.depo
        self.flow.xgrid = None

        reassignID = np.where(parentIDs < len(parentIDs))[0]
        if(len(reassignID)>0):
            tmpTree = cKDTree(self.flow.xycoords[len(parentIDs):,:2])
            distances, indices = tmpTree.query(self.flow.xycoords[reassignID,:2], k=1)
            indices += len(parentIDs)
            parentIDs[reassignID] = indices

        self.flow.parentIDs = parentIDs

    def rebuild_mesh(self, verbose=False):
        """
        Build TIN after 3D displacements.
        """

        # Build the Finite Volume representation
        self.fixIDs = self.recGrid.boundsPt + self.recGrid.edgesPt
        self.FVmesh, self.tMesh, self.lGIDs, self.inIDs, \
            self.inGIDs, self.totPts = buildMesh.reconstruct_mesh(self.recGrid,
                                                                  self.input, verbose)

        # Reset TIN kdtree and rain
        self.force.update_force_TIN(self.FVmesh.node_coords[:,:2])
        self.rain = np.zeros(self.totPts, dtype=float)
        self.rain[self.inIDs] = self.force.get_Rain(self.tNow, self.elevation, self.inIDs)

        # Update flexural isostasy
        if self.input.flexure:
            self.tinFlex = np.zeros(self.totPts, dtype=float)
            self.flex.update_flexure_parameters(self.FVmesh.node_coords[:,:2])

        # Update stratigraphic mesh
        if self.input.stratdx>0:
            self.strata.update_TIN(self.FVmesh.node_coords[:, :2])

        # Update erodibility maps
        if self.input.erolays is None:
            self.flow.erodibility = np.full(self.totPts, self.input.SPLero)
        else:
            self.flow.erodibility = self.mapero.erodibility

        self.flow.xycoords = self.FVmesh.node_coords[:, :2]
        self.flow.xgrid = None
        self.flow.sedload = None

    def run_to_time(self, tEnd, profile=False, verbose=False):
        """
        Run the simulation to a specified point in time (tEnd).

        Parameters
        ----------
        tEnd : float
            Run the simulation to this many years.

        profile : bool
            If True, dump cProfile output to /tmp.

        verbose : bool
            If True, output additional debug information.
        """
        if profile:
            pid = os.getpid()
            pr = cProfile.Profile()
            pr.enable()

        assert hasattr(self, 'recGrid'), "DEM file has not been loaded. Configure one in your XML file or call the build_mesh function."

        if tEnd > self.input.tEnd:
            if self._rank == 0:
                print 'Specified end time is greater than the one used in the XML input file and has been adjusted!'
            tEnd = self.input.tEnd

        # Define non-flow related processes times
        if not self.simStarted:
            self.force.next_rain = self.force.T_rain[0, 0]
            self.force.next_disp = self.force.T_disp[0, 0]
            self.force.next_display = self.input.tStart
            if self.input.laytime>0:
                self.force.next_layer = self.input.tStart + self.input.laytime
            else:
                self.force.next_layer = self.input.tEnd + 1000.
            self.exitTime = self.input.tEnd
            if self.input.flexure:
                self.force.next_flexure = self.input.tStart + self.input.ftime
            else:
                self.force.next_flexure = self.exitTime + self.input.tDisplay
            self.simStarted = True

        outStrata = 0
        last_time = time.clock()
        last_output = time.clock()

        # Perform main simulation loop
        while self.tNow < tEnd:
            # At most, display output every 5 seconds
            tloop = time.clock() - last_time
            if self._rank == 0 and time.clock() - last_output >= 5.0:
                print 'tNow = %s (step took %0.02f seconds)' % (self.tNow, tloop)
                last_output = time.clock()
            last_time = time.clock()

            # Load precipitation rate
            if self.force.next_rain <= self.tNow and self.force.next_rain < self.input.tEnd:
                if self.tNow == self.input.tStart:
                    self.force.getSea(self.tNow)
                self.rain = np.zeros(self.totPts, dtype=float)
                self.rain[self.inIDs] = self.force.get_Rain(self.tNow, self.elevation, self.inIDs)
                self._comm.Allreduce(mpi.IN_PLACE, self.rain, op=mpi.MAX)

            # Load tectonic grid
            if not self.input.disp3d:
                # Vertical displacements
                if self.force.next_disp <= self.tNow and self.force.next_disp < self.input.tEnd:
                    ldisp = np.zeros(self.totPts, dtype=float)
                    ldisp.fill(-1.e6)
                    ldisp[self.inIDs] = self.force.load_Tecto_map(self.tNow,self.inIDs)
                    self._comm.Allreduce(mpi.IN_PLACE, ldisp, op=mpi.MAX)
                    self.disp = self.force.disp_border(ldisp, self.FVmesh.neighbours,
                                                       self.FVmesh.edge_length, self.recGrid.boundsPt)
                    self.applyDisp = True
            else:
                # 3D displacements
                if self.force.next_disp <= self.tNow and self.force.next_disp < self.input.tEnd:
                    if self.input.laytime == 0:
                        updateMesh = self.force.load_Disp_map(self.tNow, self.FVmesh.node_coords[:, :2], self.inIDs)
                    else:
                        # Define 3D displacements on the stratal regions
                        if self.strata is not None:
                            updateMesh, regdX, regdY = self.force.load_Disp_map(self.tNow, self.FVmesh.node_coords[:, :2],
                                                                  self.inIDs, True, self.strata.xyi, self.strata.ids)
                        else:
                            updateMesh = self.force.load_Disp_map(self.tNow, self.FVmesh.node_coords[:, :2], self.inIDs)

                    # Update mesh when a 3D displacements field has been loaded
                    if updateMesh:
                        self.force.dispZ = self.force.disp_border(self.force.dispZ, self.FVmesh.neighbours,
                                           self.FVmesh.edge_length, self.recGrid.boundsPt)
                        # Define flexural flags
                        fflex = 0
                        flexiso = None
                        if self.input.flexure:
                            flexiso = self.cumflex
                            fflex = 1
                        # Define stratal flags
                        fstrat = 0
                        sload = None
                        if self.input.udw == 1 and self.tNow == self.input.tStart and self.strata is not None:
                            self.strata.oldload = np.zeros(len(self.elevation), dtype=float)
                        if self.strata is not None:
                            if self.strata.oldload is None:
                                self.strata.oldload = np.zeros(len(self.elevation), dtype=float)
                        if self.input.laytime > 0 and self.strata.oldload is not None:
                            sload = self.strata.oldload
                            fstrat = 1
                        # Define erodibility map flags
                        fero = 0
                        vKe = None
                        vTh = None
                        if self.input.erolays >= 0:
                            fero = 1
                            vKe = self.mapero.Ke
                            vTh = self.mapero.thickness
                        # Apply horizontal displacements
                        self.recGrid.tinMesh, self.elevation, self.cumdiff, fcum, scum, Ke, Th = self.force.apply_XY_dispacements(
                            self.recGrid.areaDel, self.fixIDs, self.elevation, self.cumdiff, tflex=flexiso, scum=sload, Te=vTh,
                            Ke=vKe, flexure=fflex, strat=fstrat, ero=fero)
                        # Update relevant parameters in deformed TIN
                        if fflex == 1:
                            self.cumflex = fcum
                        if fero == 1:
                            self.mapero.Ke = Ke
                            self.mapero.thickness = Th
                        # Rebuild the computational mesh
                        self.rebuild_mesh(verbose)
                        # Update the stratigraphic mesh
                        if self.input.laytime > 0 and self.strata is not None:
                            self.strata.move_mesh(regdX, regdY, scum, verbose)

            # Compute stream network
            self.fillH, self.elevation = buildFlux.streamflow(self.input, self.FVmesh, self.recGrid, self.force, self.hillslope, \
                                              self.flow, self.elevation, self.lGIDs, self.rain, self.tNow, verbose)

            # Compute isostatic flexure
            if self.tNow >= self.force.next_flexure:
                flextime = time.clock()
                self.force.getSea(self.tNow)
                self.tinFlex = self.flex.get_flexure(self.elevation, self.cumdiff,
                            self.force.sealevel,self.recGrid.boundsPt, initFlex=False)
                # Get border values
                self.tinFlex = self.force.disp_border(self.tinFlex, self.FVmesh.neighbours,
                                                      self.FVmesh.edge_length, self.recGrid.boundsPt)
                # Update flexural parameters
                self.elevation += self.tinFlex
                self.cumflex += self.tinFlex
                # Update next flexure time
                self.force.next_flexure += self.input.ftime
                if self._rank == 0:
                    print "   - Compute flexural isostasy ", time.clock() - flextime

            # Create checkpoint files and write HDF5 output
            if self.tNow >= self.force.next_display:
                if self.force.next_display > self.input.tStart:
                    outStrata = 1
                checkPoints.write_checkpoints(self.input, self.recGrid, self.lGIDs, self.inIDs, self.tNow,
                                            self.FVmesh, self.tMesh, self.force, self.flow, self.rain,
                                            self.elevation, self.fillH, self.cumdiff, self.outputStep,
                                            self.mapero, self.cumflex)
                # Update next display time
                self.force.next_display += self.input.tDisplay
                self.outputStep += 1
                last_output = time.clock()

                # self.straTIN.write_hdf5_stratigraphy(0,0)
                # exit

            # Update next stratal layer time
            if self.tNow >= self.force.next_layer:
                self.force.next_layer += self.input.laytime
                if self.strata:
                    self.strata.buildStrata(self.elevation, self.cumdiff, self.force.sealevel,
                        self._rank, outStrata, self.outputStep-1)
                outStrata = 0

            # Get the maximum time before updating one of the above processes / components
            tStop = min([self.force.next_display, self.force.next_layer, self.force.next_flexure,
                        tEnd, self.force.next_disp, self.force.next_rain])

            # Compute sediment transport up to tStop
            self.tNow, self.elevation, self.cumdiff = buildFlux.sediment_flux(self.input, self.recGrid, self.hillslope, self.FVmesh,
                              self.tMesh, self.flow, self.force, self.rain, self.lGIDs, self.applyDisp, self.mapero, self.cumdiff, \
                              self.fillH, self.disp, self.inGIDs, self.elevation, self.tNow, tStop, verbose)

        tloop = time.clock() - last_time
        if self._rank == 0:
            print 'tNow = %s (%0.02f seconds)' % (self.tNow, tloop)

        # Isostatic flexure
        if self.input.flexure:
            flextime = time.clock()
            self.force.getSea(self.tNow)
            self.tinFlex = self.flex.get_flexure(self.elevation, self.cumdiff,
                        self.force.sealevel,self.recGrid.boundsPt,initFlex=False)
            # Get border values
            self.tinFlex = self.force.disp_border(self.tinFlex, self.FVmesh.neighbours,
                                                  self.FVmesh.edge_length, self.recGrid.boundsPt)
            # Update flexural parameters
            self.elevation += self.tinFlex
            self.cumflex += self.tinFlex
            # Update next flexure time
            self.force.next_flexure += self.input.ftime
            if self._rank == 0:
                print "   - Compute flexural isostasy ", time.clock() - flextime

        # Create checkpoint files and write HDF5 output
        if self.input.udw == 0 or self.tNow == self.input.tEnd or self.tNow == self.force.next_display:
            checkPoints.write_checkpoints(self.input, self.recGrid, self.lGIDs, self.inIDs, self.tNow, \
                                self.FVmesh, self.tMesh, self.force, self.flow, self.rain, \
                                self.elevation, self.fillH, self.cumdiff, self.outputStep, self.mapero, \
                                self.cumflex)
            self.force.next_display += self.input.tDisplay
            self.outputStep += 1

        # Update next stratal layer time
        if self.tNow >= self.force.next_layer:
            self.force.next_layer += self.input.laytime
            self.strata.buildStrata(self.elevation, self.cumdiff, self.force.sealevel,
                                    self._rank, 1, self.outputStep-1)

        if profile:
            pr.disable()
            s = StringIO.StringIO()
            sortby = 'cumulative'
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.dump_stats('/tmp/profile-%d' % pid)

    def ncpus(self):
        """Return the number of CPUs used to generate the results."""
        return 1
