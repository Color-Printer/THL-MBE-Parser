# THL-MBE-Parser
For unpacking and repacking MBE data files from The Hundred Line.

Thanks to Ahtheerr for making the original version of this script...presumably. That's where I got it from, though the repo is now gone.

The original version of this script was not perfect. It could not handle certain things such as two-byte short values, and did not handle table offsets correctly (in a way that only affected about 1% of the MBE files - go figure). I have made adjustments (including rewriting comments and print statements from Spanish into English), so now both the Parser and the Repacker scripts work on ***every MBE data file in the game***. This includes the text ones, too.

The Repacker script currently does not work with CSV files unpacked from MBEs with MVGLToolsCLI. I *might* add this functionality later but for now it can only repack csv files that have been dumped via the Parser script.

This script requires **python** to run. *(At least version 3.8 should be good? I think?)*

## Usage
Note that MBEs will need to be unpacked from the MVGL archive files. Might I suggest [MVGLTools](https://github.com/SydMontague/MVGLTools)? (Again, just don't use the MBE-specific unpacking features for right now)

### MBE_Parser.py
`python MBE_Parser.py <filepath.mbe>`

Outputs a directory called `[filename]` containing each sheet from the MBE file in its own comma-separated value (CSV) file, filename formatted like `[sheet number]_[sheet name].csv`.

### MBE_Repacker.py
`python MBE_Repacker.py <MBE_directory_filepath>`

Takes in a directory of CSV files (filenames formatted like `[sheet number]_[sheet name].csv`) and outputs a packed MBE file called `[directory name].mbe`.

Note that re-packed MBE files that have not been altered are still likely different from their original form due to some inconsistencies with byte padding. However, this _shouldn't_ matter in-game, and all unpacked CSV files from all of the game's MBE packs are identical when unpacked-repacked-unpacked again.
