import { a } from "x";

class Child extends Base {
  method(x) {
    function inner(y) {
      return helper(y);
    }

    return helper(x) + inner(x);
  }
}

function helper(x) {
  return x;
}

