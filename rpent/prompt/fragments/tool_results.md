Every tool result carries `call_ok` and `execution_status`. `call_ok` only means
the call was valid and the framework handled it; it never means the action
succeeded. `execution_status` is `completed`, `partial`, `not_started`,
`rejected`, or `unknown`. `no_execution` appears only when the call produced no
physical action, and `execution_uncertain` appears only when an interrupted call
may have outlived the request and must be verified before retrying.
