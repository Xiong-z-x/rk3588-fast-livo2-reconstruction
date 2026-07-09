# Mechanical Design Sources

This directory stores the mechanical design source files used by the project.

## Source Package

`solidworks_sources/` is imported from the local design source directory `D:\solidworks`. It contains the E200 UAV platform, handheld acquisition fixture and embedded mounting structures used around the Livox Mid-360, Hikrobot camera and RK3588/ELF2-class board.

Imported source summary:

| Directory | Content |
| --- | --- |
| `solidworks_sources/E200/` | UAV platform assembly, propulsion/motor models, board mounting parts and imported component models |
| `solidworks_sources/手持件/` | Handheld data-acquisition fixture assembly and part files |
| `solidworks_sources/嵌入式/` | Embedded board, LiDAR-camera mounting and protective-shell design variants |

File summary after excluding SolidWorks temporary lock files:

| Type | Count | Size |
| --- | ---: | ---: |
| SolidWorks assemblies `.SLDASM/.sldasm` | 513 | 135.44 MB |
| SolidWorks parts `.SLDPRT/.sldprt` | 172 | 126.59 MB |
| STEP models `.STEP/.step` | 3 | 52.71 MB |
| STL models `.STL/.stl` | 3 | 1.14 MB |
| 3MF reference models `.3MF/.3mf` | 3 | 0.31 MB |
| PNG reference images `.png` | 3 | 2.67 MB |

CAD files are tracked with Git LFS.
