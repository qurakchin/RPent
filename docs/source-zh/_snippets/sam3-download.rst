.. code-block:: bash

   # Hugging Face：先在模型页申请访问权限，再执行 hf auth login。
   hf download facebook/sam3 sam3.pt --local-dir ./checkpoints/sam3

   # ModelScope：与上面的 Hugging Face 命令二选一。
   modelscope download --model facebook/sam3 sam3.pt --local_dir ./checkpoints/sam3

   export SAM3_CHECKPOINT_PATH="$PWD/checkpoints/sam3/sam3.pt"
