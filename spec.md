# Project Specification

## What do you want to build?

There exist three major hardware system setups, primarily here:
https://github.com/riscv-boom/riscv-boom 
https://github.com/chipsalliance/rocket-chip/tree/master/src/main 
https://github.com/openhwgroup/cva6/tree/master/core 

Your initial job now is to closely analyse and understand each of their structures, goals and the overall setups.

There is another HDL Language called Anvil:
documentation: https://docs.anvil.kisp-lab.org/languageReference.html
Some background about it: https://docs.anvil.kisp-lab.org/background.html Motivation behind it: https://docs.anvil.kisp-lab.org/helloWorld.html The idea of communication: https://docs.anvil.kisp-lab.org/communication.html
The goal is to create a comprehensive translation for all three:
https://github.com/riscv-boom/riscv-boom 
https://github.com/chipsalliance/rocket-chip/tree/master/src/main 
https://github.com/openhwgroup/cva6/tree/master/core 

Using Anvil

Now there are two ways of accomplishing this task, both must be done in parallel.

Given in the workspace is sv2anvil.py. You need to refer to(in no way is it comprehensive and it must be improved using recursive testing as and when you progress for this task). Then using it, you need to construct the anvil implementations of the above 3. You need to compile the converted Anvil code back to SV, check if its implementation is similar to the original, if not modify the sv2anv.py and then continue. This needs to continue until the perfect Anvil translation for the above three setups has been created.
Given in the workspace is the agent_spec.md and worker_Skill.md(these are simple instructions for creating a worker, one that follows those exact instructions to convert SV code to Anvil). These instructions are not perfect and would have to be modified as we proceed down the line. Workers with such skills need to be created and then used to create corresponding Anvil setups for each of the above three. Those anvil setups then need to be compiled and their compiled SV codes need to be compared with the original setup. If the implementation is not similar/identical, the inadequacies need to be noted and then addressed by modifying the agent_spec.md and the worker_skill.md. This cycle must continue until the perfect Anvil implementation for all the above three setups has been created.
A tricky part in this conversion from SV to Anvil would be handling the timing. A number of iterations would be required for this, do keep a timing_handling.md which summarise the steps taken to understand and handle the timing conversion between the languages.

## How do you consider the project is success?

This is a success if all three setups have been succesfully converted to Anvil(including handling the timing and related information). The anvil code is compiled into its SV version and if that version is akin to the initial setup , then this conversion project has been successful
