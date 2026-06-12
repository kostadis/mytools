# Rules


We are building a replacement for the /home/kroussos/src/mytools/pdf-translators/adventure_model.py code. It will have two parts, a rust core, that does the parsing, and a separate interface that integrates with the python code. no python code can penetrate the rust core.  

The plan for the code is in PLAN2.md

Some of the code has been written. Before writing new code, you must read PLAN2.md and read the code. 

Once you have done that, you must compile the code. 

Every time we edit code or start the project we must make sure the code compiles. 

All code that gets written must be tested for compilation.

No file can have more than 500 lines of text. If the files get to 600 lines, split the file into at least two. One of the files can be much smaller than other. 

Use stepwise refinement. First define the class hierarchy and implement that. Compile the code. Then for each write the methods as empty stubs. And verify that compiles and runs. Then implement the functionality. 

After every edit, run 'cargo build'

if the code has any compile errors, fix the compile errors and then continue with the next step. 


