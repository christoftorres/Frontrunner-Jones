{
  trace: [],
  callstack: [],
  
  step: function(log, db) {
    switch(log.op.toString()) {
      case "SUICIDE": case "SELFDESTRUCT":
        this.trace.push({"call_type": log.op.toString(), "from": toHex(log.contract.getAddress()), "to": toHex(toAddress(log.stack.peek(0).toString(16))), "gasCost": log.getCost(), "gasIn": log.getGas(), "input": null, "output": null, "value": null, "depth": log.getDepth(), "error": log.getError(), "result": 1});
        return;
      case "CREATE": case "CREATE2":
        this.callstack.push({"call_type": log.op.toString(), "from": toHex(log.contract.getAddress()), "to": null, "input": toHex(log.memory.slice(log.stack.peek(1).valueOf(), log.stack.peek(1).valueOf() + log.stack.peek(2).valueOf())), "output": null, "value": log.stack.peek(0).valueOf(), "depth": log.getDepth(), "error": log.getError(), "result": 1});
        return;
      case "CALL": case "CALLCODE":
        this.callstack.push({"call_type": log.op.toString(), "from": toHex(log.contract.getAddress()), "to": toHex(toAddress(log.stack.peek(1).toString(16))), "input": toHex(log.memory.slice(log.stack.peek(3).valueOf(), log.stack.peek(3).valueOf() + log.stack.peek(4).valueOf())), "output": null, "output_offset": log.stack.peek(5).valueOf(), "output_size": log.stack.peek(6).valueOf(), "value": log.stack.peek(2).valueOf(), "depth": log.getDepth(), "error": log.getError(), "result": 1});
        return;
      case "DELEGATECALL": case "STATICCALL":
        this.callstack.push({"call_type": log.op.toString(), "from": toHex(log.contract.getAddress()), "to": toHex(toAddress(log.stack.peek(1).toString(16))), "input": toHex(log.memory.slice(log.stack.peek(2).valueOf(), log.stack.peek(2).valueOf() + log.stack.peek(3).valueOf())), "output": null, "output_offset": log.stack.peek(4).valueOf(), "output_size": log.stack.peek(5).valueOf(), "value": 0, "depth": log.getDepth(), "error": log.getError(), "result": 1});
        return;
      default:
        break;
    };
    if (log.getDepth() == this.callstack.length) {
      var call = this.callstack.pop();
      if (call.call_type == 'CREATE' || call.call_type == "CREATE2") {
        var return_value = log.stack.peek(0);
        if (!return_value.equals(0)) {
          call.result = 0;
          call.to     = toHex(toAddress(return_value.toString(16)));
          call.output = toHex(db.getCode(toAddress(return_value.toString(16))));
        };
      } else {
        var return_value = log.stack.peek(0);
        if (!return_value.equals(0)) {
          call.result = 0;
          call.output = toHex(log.memory.slice(call.output_offset, call.output_offset + call.output_size));
        };
        delete call.output_offset; delete call.output_size;
      };
      this.trace.push(call);
    };
  },

  fault: function(log, db) {},

  result: function(ctx, db) {
    return this.trace;
  }
}
