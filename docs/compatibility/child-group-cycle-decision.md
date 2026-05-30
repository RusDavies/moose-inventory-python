# Child-group cycle compatibility decision

Ruby `moose-inventory` is the compatibility oracle for this Python CLI replacement. During the child-group command port, the Python implementation initially rejected circular group relationships such as `parent -> child` followed by `child -> parent`.

A direct Ruby/Python parity check showed that the current Ruby CLI accepts that second association successfully. To preserve CLI interchangeability, the Python implementation now follows Ruby behavior and permits the association.

This is a compatibility decision, not an endorsement of cyclic inventory hierarchies as a good modeling practice. If the Ruby CLI later changes to reject cycles, the Python parity manifest case `group-addchild-circular-ruby-compatible` should be updated and the Python command can adopt the stricter behavior at the same compatibility boundary.
