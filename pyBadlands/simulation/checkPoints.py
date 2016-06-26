##~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~##
##                                                                                   ##
##  This file forms part of the Badlands surface processes modelling application.    ##
##                                                                                   ##
##  For full license and copyright information, please refer to the LICENSE.md file  ##
##  located at the project root, or contact the authors.                             ##
##                                                                                   ##
##~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~##
"""
This file is used to checkpoint and is the main entry to write simulation output.
"""

import time
import numpy as np
import mpi4py.MPI as mpi

from pyBadlands import (visualiseFlow, visualiseTIN, eroMesh)

def write_checkpoints(input, recGrid, lGIDs, inIDs, tNow, FVmesh, \
                      tMesh, force, flow, rain, elevation, cumdiff, \
                      step, mapero=None, cumflex=None):
    """
    Create the checkpoint files (used for HDF5 output).
    """

    rank = mpi.COMM_WORLD.rank
    size = mpi.COMM_WORLD.size
    comm = mpi.COMM_WORLD

    out_time = time.clock()
    visXlim = np.zeros(2)
    visYlim = np.zeros(2)
    visXlim[0] = recGrid.rectX.min()
    visXlim[1] = recGrid.rectX.max()
    visYlim[0] = recGrid.rectY.min()
    visYlim[1] = recGrid.rectY.max()

    # Done when TIN has been built/rebuilt
    outPts, outCells = visualiseTIN.output_cellsIDs(lGIDs, inIDs, visXlim, visYlim,
                                        FVmesh.node_coords[:, :2], tMesh.cells)
    tcells = np.zeros(size)
    tcells[rank] = len(outCells)
    comm.Allreduce(mpi.IN_PLACE, tcells, op=mpi.MAX)
    tnodes = np.zeros(size)
    tnodes[rank] = len(lGIDs)
    comm.Allreduce(mpi.IN_PLACE, tnodes, op=mpi.MAX)

    # Done for every visualisation step
    flowIDs, polylines = visualiseFlow.output_Polylines(outPts, flow.receivers[outPts],
                visXlim, visYlim, FVmesh.node_coords[:, :2])
    fnodes = np.zeros(size)
    fnodes[rank] = len(flowIDs)
    comm.Allreduce(mpi.IN_PLACE, fnodes, op=mpi.MAX)
    fline = np.zeros(size)
    fline[rank] = len(polylines[:, 0])
    comm.Allreduce(mpi.IN_PLACE, fline, op=mpi.MAX)

    # Compute flow parameters
    flow.compute_parameters()

    # Write HDF5 files
    if input.flexure:
        visualiseTIN.write_hdf5_flexure(input.outDir, input.th5file, step, tMesh.node_coords[:,:2],
                                    elevation[lGIDs], rain[lGIDs], flow.discharge[lGIDs],
                                    cumdiff[lGIDs], cumflex[lGIDs], outCells, rank, input.oroRain)
    else:
        visualiseTIN.write_hdf5(input.outDir, input.th5file, step, tMesh.node_coords[:,:2],
                                elevation[lGIDs], rain[lGIDs], flow.discharge[lGIDs],
                                cumdiff[lGIDs], outCells, rank, input.oroRain)

    visualiseFlow.write_hdf5(input.outDir, input.fh5file, step, FVmesh.node_coords[flowIDs, :2],
                             elevation[flowIDs], flow.discharge[flowIDs], flow.chi[flowIDs],
                             flow.basinID[flowIDs], polylines, rank)

    # Combine HDF5 files and write time series
    if rank == 0:
        visualiseTIN.write_xmf(input.outDir, input.txmffile, input.txdmffile, step, tNow,
                           tcells, tnodes, input.th5file, force.sealevel, size,
                           input.flexure, input.oroRain)
        visualiseFlow.write_xmf(input.outDir, input.fxmffile, input.fxdmffile, step, tNow,
                            fline, fnodes, input.fh5file, size)
        print "   - Writing outputs (%0.02f seconds; tNow = %s)" % (time.clock() - out_time, tNow)

    # Record erodibility maps
    if input.erolays >= 0 and rank == 0:
        mapero.write_hdf5_erolay(step)
