##~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~##
##                                                                                   ##
##  This file forms part of the Badlands surface processes modelling application.    ##
##                                                                                   ##
##  For full license and copyright information, please refer to the LICENSE.md file  ##
##  located at the project root, or contact the authors.                             ##
##                                                                                   ##
##~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~##
"""
This module exports the TIN surface with associated parameters based on hdf5.
"""

import time
import h5py
import numpy
import xml.etree.ElementTree as ETO

def output_cellsIDs(allIDs, inIDs, visXlim, visYlim, coords, cells):
    """
    This function defines the cells used for visualising the TIN surface.

    Parameters
    ----------
    variable : allIDs
        Numpy integer-type array filled with the global vertex IDs for each local grid located
        within the partition (including those on the edges).

    variable: inIDs
        Numpy integer-type array filled with the global vertex IDs for each local grid located
        within the partition (not those on the edges).

    variable: visXlim, visYlim
        Numpy array containing the extent of visualisation grid.

    variable: coords
        Numpy float-type array containing X, Y coordinates of the local TIN nodes.

    variable: cells
        Numpy integer-type array filled with the global cell IDs.

    Return
    ----------
    variable: outPts
        Numpy integer-type array containing the output node IDs.

    variable: cells
        Numpy integer-type array containing the output cell IDs.
    """

    # Find non-overlapping vertices in each local TIN
    findInside = numpy.in1d(allIDs, inIDs)
    inside = numpy.where(findInside == True)

    # Find cells containing only the inside indices
    inCell = numpy.in1d(cells, inside).reshape(cells.shape)
    intCell = 1*inCell
    sumCell = intCell.sum(axis=1)
    localCell = numpy.where(sumCell>0)[0]
    outcell = cells[localCell]

    # Get the non-border points IDs
    notBorder = numpy.where((coords[allIDs,0] >= visXlim[0]) & (coords[allIDs,0] <= visXlim[1]) &
                         (coords[allIDs,1] >= visYlim[0]) & (coords[allIDs,1] <= visYlim[1]) )[0]
    notBorderIDs = numpy.zeros(len(allIDs),dtype=int)
    notBorderIDs.fill(-1)
    notBorderIDs[notBorder] = allIDs[notBorder]
    findInside2 = numpy.in1d(allIDs, notBorderIDs)
    inside2 = numpy.where(findInside2 == True)

    inCell2 = numpy.in1d(outcell, inside2).reshape(outcell.shape)
    intCell2 = 1*inCell2
    sumCell2 = intCell2.sum(axis=1)
    localCell2 = numpy.where(sumCell2>2)[0]

    # Get inside nodes
    rav = numpy.ravel(outcell[localCell2])
    allInside = numpy.unique(rav)

    return allIDs[allInside], outcell[localCell2] + 1

def write_hdf5(folder, h5file, step, coords, elevation, rain, discharge, cumdiff, cells, rank, rainOn):
    """
    This function writes for each processor the HDF5 file containing surface information.

    Parameters
    ----------
    variable : folder
        Name of the output folder.

    variable: h5file
        First part of the hdf5 file name.

    variable: step
        Output visualisation step.

    variable : coords
        Numpy float-type array containing X, Y coordinates of the local TIN nodes.

    variable : elevation
        Numpy float-type array containing Z coordinates of the local TIN nodes.

    variable : rain
        Numpy float-type array containing rain value of the local TIN nodes.

    variable : discharge
        Numpy float-type array containing the discharge values of the local TIN.

    variable : cumdiff
        Numpy float-type array containing the cumulative elevation changes values of the local TIN.

    variable: cells
        Numpy integer-type array filled with the global cell IDs.

    variable : rank
        ID of the local partition.

    variable : rainOn
        Boolean for orographic precipitation.
    """

    h5file = folder+'/'+h5file+str(step)+'.p'+str(rank)+'.hdf5'
    with h5py.File(h5file, "w") as f:

        # Write node coordinates and elevation
        f.create_dataset('coords',shape=(len(elevation),3), dtype='float32', compression='gzip')
        f["coords"][:,:2] = coords
        f["coords"][:,2] = elevation

        f.create_dataset('cells',shape=(len(cells[:,0]),3), dtype='int32', compression='gzip')
        f["cells"][:,:] = cells

        f.create_dataset('discharge',shape=(len(discharge), 1), dtype='float32', compression='gzip')
        f["discharge"][:,0] = discharge

        if rainOn:
            f.create_dataset('precipitation',shape=(len(discharge), 1), dtype='float32', compression='gzip')
            f["precipitation"][:,0] = rain

        f.create_dataset('cumdiff',shape=(len(discharge), 1), dtype='float32', compression='gzip')
        f["cumdiff"][:,0] = cumdiff

def write_hdf5_flexure(folder, h5file, step, coords, elevation, rain, discharge, cumdiff, cumflex, cells, rank, rainOn):
    """
    This function writes for each processor the HDF5 file containing surface information.

    Parameters
    ----------
    variable : folder
        Name of the output folder.

    variable: h5file
        First part of the hdf5 file name.

    variable: step
        Output visualisation step.

    variable : coords
        Numpy float-type array containing X, Y coordinates of the local TIN nodes.

    variable : elevation
        Numpy float-type array containing Z coordinates of the local TIN nodes.

    variable : rain
        Numpy float-type array containing rain value of the local TIN nodes.

    variable : discharge
        Numpy float-type array containing the discharge values of the local TIN.

    variable : cumdiff
        Numpy float-type array containing the cumulative elevation changes values of the local TIN.

    variable : cumdiff
        Numpy float-type array containing the cumulative flexural changes values of the local TIN.

    variable: cells
        Numpy integer-type array filled with the global cell IDs.

    variable : rank
        ID of the local partition.

    variable : rainOn
        Boolean for orographic precipitation.
    """

    h5file = folder+'/'+h5file+str(step)+'.p'+str(rank)+'.hdf5'
    with h5py.File(h5file, "w") as f:

        # Write node coordinates and elevation
        f.create_dataset('coords',shape=(len(elevation),3), dtype='float32', compression='gzip')
        f["coords"][:,:2] = coords
        f["coords"][:,2] = elevation

        f.create_dataset('cells',shape=(len(cells[:,0]),3), dtype='int32', compression='gzip')
        f["cells"][:,:] = cells

        f.create_dataset('discharge',shape=(len(discharge), 1), dtype='float32', compression='gzip')
        f["discharge"][:,0] = discharge

        if rainOn:
            f.create_dataset('precipitation',shape=(len(discharge), 1), dtype='float32', compression='gzip')
            f["precipitation"][:,0] = rain

        f.create_dataset('cumdiff',shape=(len(discharge), 1), dtype='float32', compression='gzip')
        f["cumdiff"][:,0] = cumdiff

        f.create_dataset('cumflex',shape=(len(discharge), 1), dtype='float32', compression='gzip')
        f["cumflex"][:,0] = cumflex

def _write_xdmf(folder, xdmffile, xmffile, step):
    """
    This function writes the XDmF file which is calling the XmF file.

    Parameters
    ----------
    variable : folder
        Name of the output folder.

    variable: xdmffile
        XDmF file name.

    variable: xmffile
        First part of the XmF file name.

    variable: step
        Output visualisation step.
    """

    f= open(folder+'/'+xdmffile,'w')

    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write('<!DOCTYPE Xdmf SYSTEM "Xdmf.dtd">\n')
    f.write('<Xdmf Version="2.0" xmlns:xi="http://www.w3.org/2001/XInclude">\n')
    f.write(' <Domain>\n')
    f.write('    <Grid GridType="Collection" CollectionType="Temporal">\n')

    for p in range(step+1):
        xfile = xmffile+str(p)+'.xmf'
        f.write('      <xi:include href="%s" xpointer="xpointer(//Xdmf/Domain/Grid)"/>\n' %xfile)

    f.write('    </Grid>\n')
    f.write(' </Domain>\n')
    f.write('</Xdmf>\n')
    f.close()

    return

def write_xmf(folder, xmffile, xdmffile, step, time, elems, nodes, h5file, sealevel, size, flexOn, rainOn):
    """
    This function writes the XmF file which is calling each HFD5 file.

    Parameters
    ----------
    variable : folder
        Name of the output folder.

    variable: xmffile
        First part of the XmF file name.

    variable: step
        Output visualisation step.

    variable : time
        Simulation time.

    variable : elems
        Numpy integer-type array containing the number of cells of each local partition.

    variable : nodes
        Numpy integer-type array containing the number of nodes of each local partition.

    variable : nodes
        Numpy float-type array containing the discharge values of the local TIN.

    variable: h5file
        First part of the hdf5 file name.

    variable: sealevel
        Sealevel elevation.

    variable : size
        Number of partitions.

    variable : flexOn
        Boolean for flexural isostasy.

    variable : rainOn
        Boolean for orographic precipitation.
    """

    xmf_file = folder+'/'+xmffile+str(step)+'.xmf'
    f= open(str(xmf_file),'w')

    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write('<!DOCTYPE Xdmf SYSTEM "Xdmf.dtd">\n')
    f.write('<Xdmf Version="2.0" xmlns:xi="http://www.w3.org/2001/XInclude">\n')
    f.write(' <Domain>\n')
    f.write('    <Grid GridType="Collection" CollectionType="Spatial">\n')
    f.write('      <Time Type="Single" Value="%s"/>\n'%time)

    for p in range(size):
        pfile = h5file+str(step)+'.p'+str(p)+'.hdf5'
        f.write('      <Grid Name="Block.%s">\n' %(str(p)))
        f.write('         <Topology Type="Triangle" NumberOfElements="%d" BaseOffset="1">\n'%elems[p])
        f.write('          <DataItem Format="HDF" DataType="Int" ')
        f.write('Dimensions="%d 3">%s:/cells</DataItem>\n'%(elems[p],pfile))
        f.write('         </Topology>\n')

        f.write('         <Geometry Type="XYZ">\n')
        f.write('          <DataItem Format="HDF" NumberType="Float" Precision="4" ')
        f.write('Dimensions="%d 3">%s:/coords</DataItem>\n'%(nodes[p],pfile))
        f.write('         </Geometry>\n')

        f.write('         <Attribute Type="Scalar" Center="Node" Name="Discharge">\n')
        f.write('          <DataItem Format="HDF" NumberType="Float" Precision="4" ')
        f.write('Dimensions="%d 1">%s:/discharge</DataItem>\n'%(nodes[p],pfile))
        f.write('         </Attribute>\n')

        f.write('         <Attribute Type="Scalar" Center="Node" Name="Cumdiff">\n')
        f.write('          <DataItem Format="HDF" NumberType="Float" Precision="4" ')
        f.write('Dimensions="%d 1">%s:/cumdiff</DataItem>\n'%(nodes[p],pfile))
        f.write('         </Attribute>\n')

        if flexOn:
            f.write('         <Attribute Type="Scalar" Center="Node" Name="Cumflex">\n')
            f.write('          <DataItem Format="HDF" NumberType="Float" Precision="4" ')
            f.write('Dimensions="%d 1">%s:/cumflex</DataItem>\n'%(nodes[p],pfile))
            f.write('         </Attribute>\n')

        if rainOn:
            f.write('         <Attribute Type="Scalar" Center="Node" Name="Rain">\n')
            f.write('          <DataItem Format="HDF" NumberType="Float" Precision="4" ')
            f.write('Dimensions="%d 1">%s:/precipitation</DataItem>\n'%(nodes[p],pfile))
            f.write('         </Attribute>\n')

        f.write('         <Attribute Type="Scalar" Center="Node" Name="Sealevel">\n')
        f.write('          <DataItem ItemType="Function" Function="$0 * 0.00000000001 + %f" Dimensions="%d 1">\n'%(sealevel,nodes[p]))
        f.write('           <DataItem Format="HDF" NumberType="Float" Precision="4" ')
        f.write('Dimensions="%d 1">%s:/cumdiff</DataItem>\n'%(nodes[p],pfile))
        f.write('          </DataItem>\n')
        f.write('         </Attribute>\n')

        f.write('      </Grid>\n')


    f.write('    </Grid>\n')
    f.write(' </Domain>\n')
    f.write('</Xdmf>\n')
    f.close()

    _write_xdmf(folder, xdmffile, xmffile, step)

    return
