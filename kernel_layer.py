def kernel_abort(msg: str):
    raise KernelAbort(f"[KERNEL] {msg}")
