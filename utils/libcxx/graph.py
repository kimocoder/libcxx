#===----------------------------------------------------------------------===##
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#
#===----------------------------------------------------------------------===##

import platform
import os
from collections import defaultdict
import re
import libcxx.util


class DotEmitter(object):
  def __init__(self, name):
    self.name = name
    self.node_strings = {}
    self.edge_strings = []

  def addNode(self, node):
    res = str(node.id)
    if len(node.attributes):
      attr_strs = [f'{k}="{v}"' for k, v in node.attributes.iteritems()]
      res += f" [ {', '.join(attr_strs)} ]"
    res += ';'
    assert node.id not in self.node_strings
    self.node_strings[node.id] = res

  def addEdge(self, n1, n2):
    res = f'{n1.id} -> {n2.id};'
    self.edge_strings += [res]

  def node_key(self, n):
    id = n.id
    assert id.startswith('\w*\d+')

  def emit(self):
    sorted_keys = self.node_strings.keys()
    sorted_keys.sort()
    node_definitions_list = [self.node_strings[k] for k in sorted_keys]
    node_definitions = '\n  '.join(node_definitions_list)
    edge_list = '\n  '.join(self.edge_strings)
    return '''
digraph "{name}" {{
  {node_definitions}
  {edge_list}
}}    
'''.format(name=self.name, node_definitions=node_definitions, edge_list=edge_list).strip()


class DotReader(object):
  def __init__(self):
    self.graph = DirectedGraph(None)

  def abortParse(self, msg="bad input"):
    raise Exception(msg)

  def parse(self, data):
    lines = [l.strip() for l in data.splitlines() if l.strip()]
    maxIdx = len(lines)
    idx = 0
    if not self.parseIntroducer(lines[idx]):
      self.abortParse('failed to parse introducer')
    idx += 1
    while idx < maxIdx and (self.parseNodeDefinition(lines[idx])
                            or self.parseEdgeDefinition(lines[idx])):
      idx += 1
    if idx == maxIdx or not self.parseCloser(lines[idx]):
      self.abortParse("no closing } found")
    return self.graph

  def parseEdgeDefinition(self, l):
    edge_re = re.compile('^\s*(\w+)\s+->\s+(\w+);\s*$')
    m = edge_re.match(l)
    if not m:
      return False
    n1 = m[1]
    n2 = m[2]
    self.graph.addEdge(n1, n2)
    return True

  def parseAttributes(self, raw_str):
    attribute_re = re.compile('^\s*(\w+)="([^"]+)"')
    parts = [l.strip() for l in raw_str.split(',') if l.strip()]
    attribute_dict = {}
    for a in parts:
      m = attribute_re.match(a)
      if not m:
        self.abortParse(f'Bad attribute "{a}"')
      attribute_dict[m[1]] = m[2]
    return attribute_dict

  def parseNodeDefinition(self, l):
    node_definition_re = re.compile('^\s*(\w+)\s+\[([^\]]+)\]\s*;\s*$')
    m = node_definition_re.match(l)
    if not m:
      return False
    id = m[1]
    attributes = self.parseAttributes(m[2])
    n = Node(id, edges=[], attributes=attributes)
    self.graph.addNode(n)
    return True

  def parseIntroducer(self, l):
    introducer_re = re.compile('^\s*digraph "([^"]+)"\s+{\s*$')
    m = introducer_re.match(l)
    if not m:
      return False
    self.graph.setName(m[1])
    return True

  def parseCloser(self, l):
    closer_re = re.compile('^\s*}\s*$')
    m = closer_re.match(l)
    return bool(m)

class Node(object):
  def __init__(self, id, edges=[], attributes={}):
    self.id = id
    self.edges = set(edges)
    self.attributes = dict(attributes)

  def addEdge(self, dest):
    self.edges.add(dest)

  def __eq__(self, another):
    if isinstance(another, str):
      return another == self.id
    return hasattr(another, 'id') and self.id == another.id

  def __hash__(self):
    return hash(self.id)

  def __str__(self):
    return self.attributes["label"]

  def __repr__(self):
    return self.__str__()

class DirectedGraph(object):
  def __init__(self, name=None, nodes=None):
    self.name = name
    self.nodes = set() if nodes is None else set(nodes)

  def setName(self, n):
    self.name = n

  def _getNode(self, n_or_id):
    return n_or_id if isinstance(n_or_id, Node) else self.getNode(n_or_id)

  def getNode(self, str_id):
    assert isinstance(str_id, (str, Node))
    return next((s for s in self.nodes if s == str_id), None)

  def getNodeByLabel(self, l):
    found = None
    for s in self.nodes:
      if s.attributes['label'] == l:
        assert found is None
        found = s
    return found

  def addEdge(self, n1, n2):
    n1 = self._getNode(n1)
    n2 = self._getNode(n2)
    assert n1 in self.nodes
    assert n2 in self.nodes
    n1.addEdge(n2)

  def addNode(self, n):
    self.nodes.add(n)

  def removeNode(self, n):
    n = self._getNode(n)
    for other_n in self.nodes:
      if other_n == n:
        continue
      new_edges = {e for e in other_n.edges if e != n}
      other_n.edges = new_edges
    self.nodes.remove(n)

  def toDot(self):
    dot = DotEmitter(self.name)
    for n in self.nodes:
      dot.addNode(n)
      for ndest in n.edges:
        dot.addEdge(n, ndest)
    return dot.emit()

  @staticmethod
  def fromDot(str):
    reader = DotReader()
    return reader.parse(str)

  @staticmethod
  def fromDotFile(fname):
    with open(fname, 'r') as f:
      return DirectedGraph.fromDot(f.read())

  def toDotFile(self, fname):
    with open(fname, 'w') as f:
      f.write(self.toDot())

  def __repr__(self):
    return self.toDot()

class BFS(object):
  def __init__(self, start):
    self.visited = set()
    self.to_visit = []
    self.start = start

  def __nonzero__(self):
    return len(self.to_visit) != 0

  def empty(self):
    return len(self.to_visit) == 0

  def push_back(self, node):
    assert node not in self.visited
    self.visited.add(node)
    self.to_visit += [node]

  def maybe_push_back(self, node):
    if node in self.visited:
      return
    self.push_back(node)

  def pop_front(self):
    assert len(self.to_visit)
    elem = self.to_visit[0]
    del self.to_visit[0]
    return elem

  def seen(self, n):
    return n in self.visited



class CycleFinder(object):
  def __init__(self, graph):
    self.graph = graph

  def findCycleForNode(self, n):
    assert n in self.graph.nodes
    all_cycles = []
    bfs = BFS(n)
    bfs.push_back(n)
    all_paths = {n: [n]}
    while bfs:
      n = bfs.pop_front()
      assert n in all_paths
      for e in n.edges:
        en = self.graph.getNode(e)
        if not bfs.seen(en):
          new_path = list(all_paths[n])
          new_path.extend([en])
          all_paths[en] = new_path
          bfs.push_back(en)
        if en == bfs.start:
          all_cycles += [all_paths[n]]
    return all_cycles

  def findCyclesInGraph(self):
    all_cycles = []
    for n in self.graph.nodes:
      if cycle := self.findCycleForNode(n):
        all_cycles += [(n, cycle)]
    return all_cycles
