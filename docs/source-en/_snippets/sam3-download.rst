.. code-block:: bash

   # Hugging Face: request access on the model page, then run hf auth login.
   hf download facebook/sam3 sam3.pt --local-dir ./checkpoints/sam3

   # ModelScope: use this instead of the Hugging Face command.
   modelscope download --model facebook/sam3 sam3.pt --local_dir ./checkpoints/sam3

   export SAM3_CHECKPOINT_PATH="$PWD/checkpoints/sam3/sam3.pt"
