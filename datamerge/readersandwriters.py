#!/usr/bin/env python
# coding: utf-8

"""
Overview:
========
Datamerge's reading and writing methods for filling the dataclasses information from external files, or to write 
the end result to external files. 
"""

__author__ = "Brian R. Pauw"
__contact__ = "brian@stack.nl"
__license__ = "GPLv3+"
__date__ = "2022/10/18"
__status__ = "beta"


from dmdataclasses import outputRangeObj
from dmdataclasses import rangeConfigObj
from dmdataclasses import (
    scatteringDataObj,
    mergedDataObj,
    mergeConfigObj,
)
import h5py
from pathlib import Path
import yaml
import nexusformat.nexus as nx
from typing import List
import logging


def scatteringDataObjFromNX(filename: Path) -> scatteringDataObj:
    """Returns a populated scatteringDataObj by reading the data from a Processed MOUSE NeXus file"""
    assert (
        filename.is_file()
    ), f'{filename=} cannot be accessed from {Path(".").absolute().as_posix()}'
    with h5py.File(filename, "r") as h5f:
        so = scatteringDataObj(
            Q=h5f["/processed/result/q"][()].flatten(),  # units of 1/nm
            # data['QSigma'] = h5f['/processed/result/q_errors'][()].flatten() # units of 1/nm
            I=h5f["/processed/result/data"][()].flatten(),  # nominal units of 1/(m sr)
            ISigma=h5f["/processed/result/errors"][()].flatten(),
            sampleName=h5f["/entry1/sample/name"][()],
            sampleOwner=h5f["/entry1/sample/sampleowner"][()],
            configuration=h5f["/entry1/instrument/configuration"][()],
            filename=filename,
            IUnits="1/(m sr)",
            Qunits="1/nm",
        )
    return so


def outputToNX(
    ofname: Path,
    mco: mergeConfigObj,
    mdo: mergedDataObj,
    rangeList: List[rangeConfigObj],
) -> None:
    """
    Stores the configuration, data and range list in the output file.
    """
    # remove if output file already exists:
    if ofname.is_file():
        ofname.unlink()
    # this is the way (to make nexusformat write the base structure)
    nxf = nx.NXroot()
    nxf = nxf.save(ofname)
    # now we can start:
    nxf["/datamerge/"] = nx.NXentry()
    nxf["/datamerge/mergeConfig"] = nx.NXgroup()
    for key, val in mco.items():
        if key in ["df", "outputRanges", "ranges", "maxRange"]:
            continue  # skip
        if key == "filename":
            assert isinstance(val, Path)
            val = val.as_posix()
        nxf[f"/datamerge/mergeConfig/{key}"] = nx.NXfield(val)

    # store information on the input datasets and settings:
    # logging.debug(rangeList)
    nxf["/datamerge/ranges"] = nx.NXgroup()
    for drange in rangeList:
        # link original dataset in the structure
        # nxf[f"/entry{dfn}"] = nx.NXlink("/processed", file=drange.filepath)
        nxf[f"/datamerge/ranges/range{drange.rangeId}"] = nx.NXgroup()
        for key, val in drange.items():
            logging.debug(f"{key=}, {val=}")
            if key in ["scatteringData"]:
                # nxf[
                #     f"/datamerge/ranges/range{drange.rangeId}/scatteringData"
                # ] = nx.NXgroup()
                nxf[
                    f"/datamerge/ranges/range{drange.rangeId}/scatteringData"
                ] = nx.NXdata(
                    nx.NXfield(val.I, name="I"),
                    axes=(nx.NXfield(val.Q, name="Q")),
                    errors=nx.NXfield(val.ISigma, name="ISigma"),
                )  # ISigma is the combined uncertainty estimate
                for dkey, dval in val.items():
                    if dkey in [
                        "dataLen",
                        "asPandas",
                        "qMin",
                        "qMax",
                        "qRange",
                        "returnMaskByQRange",
                        "I",
                        "Q",
                        "ISigma",
                    ]:
                        continue  # skip
                    if dkey == "filename":
                        dval = dval.as_posix()
                    nxf[
                        f"/datamerge/ranges/range{drange.rangeId}/scatteringData/{dkey}"
                    ] = nx.NXfield(dval)
                continue

            nxf[f"/datamerge/ranges/range{drange.rangeId}/{key}"] = nx.NXfield(val)

    # store the resulting binned dataset itself
    nxf[f"/datamerge/result"] = nx.NXdata(
        nx.NXfield(mdo.I, name="I"),
        axes=(nx.NXfield(mdo.Q, name="Q")),
        errors=nx.NXfield(mdo.ISigma, name="ISigma"),
    )  # ISigma is the combined uncertainty estimate

    # store the remainder of the merged data object:
    for key, val in mdo.items():
        if key in ["I", "Q", "ISigma"]:
            continue  # skip
        nxf[f"/datamerge/result/{key}"] = nx.NXfield(val)

    # nxf = nxf.save(ofname)

    # store the sample name and sample owner
    # nxf[f"/sample_name"] = self.sampleName
    # nxf[f"/sample_owner"] = self.sampleOwner
    # link the Q uncertainties:
    nxf[f"/datamerge/result/Q"].attrs["uncertainties"] = "QSigma"
    # also set as resolution for now
    nxf[f"/datamerge/result/Q"].attrs["resolutions"] = "QSigma"
    # CHECK: this should be automatic no?
    # # set the default path to follow
    nxf[f"/datamerge"].attrs["default"] = "result"
    nxf.attrs["default"] = "datamerge"

    # link main SASentry to datamerge dataset
    nxf["/entry"] = nx.NXlink("/datamerge")
    # canSAS compatibiity
    nxf["/datamerge"].attrs["canSAS_class"] = "SASentry"
    nxf["/datamerge"].attrs["version"] = "1.0"
    nxf["/datamerge/definition"] = nx.NXfield("NXcanSAS")
    nxf["/datamerge/run"] = nx.NXfield(0)
    nxf["/datamerge/title"] = nx.NXfield(
        f"merged dataset from {len(rangeList)} datasets"
    )
    nxf["/datamerge/result"].attrs["canSAS_class"] = "SASdata"
    nxf["/datamerge/result"].attrs["I_axes"] = "Q"
    nxf["/datamerge/result"].attrs["Q_indices"] = 0
    nxf["/datamerge/result/Q"].attrs["units"] = mco.outputQUnits
    nxf["/datamerge/result/I"].attrs["units"] = mco.outputIUnits
    # why doesn't this path exist?
    # nxf["/datamerge/result/ISigma"].attrs["units"] = mco.outputIUnits
    # nxf['/datamerge/result/IE'].attrs['units'] = "1/m"
    nxf.close()
    return


def mergeConfigObjFromYaml(filename: Path) -> mergeConfigObj:
    assert (
        filename.is_file()
    ), f"Merge configuration filename {filename.as_posix()} does not exist"
    with open(filename, "r") as f:
        configDict = yaml.safe_load(f)

    mcoAcceptableParameters = [  # acceptable parameters are everything in mco except underscore-starting objects and range
        i
        for i in dir(mergeConfigObj)
        if (not i.startswith("_") and not i in ["ranges", "filename", "outputRanges"])
    ]
    # now we set some of these parameters if we have them in configDict:
    mcoFeedParams = {
        k: v
        for k, v in configDict.items()
        if (v is not None and k in mcoAcceptableParameters)
    }
    # and we need to construct the ranges list:
    rList = list()
    rngAcceptableParameters = [
        i
        for i in dir(rangeConfigObj)
        if (not i.startswith("_") and not i in ["scatteringData", "scale"])
    ]
    if configDict.get("ranges") is not None:
        for rawRange in configDict.get("ranges"):
            rngFeedParams = {
                k: v
                for k, v in rawRange.items()
                if (v is not None and k in rngAcceptableParameters)
            }
            rList += [rangeConfigObj(**rngFeedParams)]
    # same for the outputRange list
    oRList = list()
    oRngAcceptableParameters = [
        i for i in dir(outputRangeObj) if (not i.startswith("_"))
    ]
    if configDict.get("outputRanges") is not None:
        for rawORange in configDict.get("outputRanges"):
            oRngFeedParams = {
                k: v
                for k, v in rawORange.items()
                if (v is not None and k in oRngAcceptableParameters)
            }
            oRList += [outputRangeObj(**oRngFeedParams)]

    mco = mergeConfigObj(
        filename=filename, **mcoFeedParams, ranges=rList, outputRanges=oRList
    )
    return mco


if __name__ == "__main__":
    """quick test"""
    so = scatteringDataObjFromNX(
        Path("datamerge")
        / "tests"
        / "data"
        / "20220925"
        / "autoproc"
        / "group_6"
        / "20220925_42_expanded_stacked_processed.nxs"
    )

    mco = mergeConfigObjFromYaml(Path("datamerge", "tests", "mergeConfigExample.yaml"))
    print(mco)