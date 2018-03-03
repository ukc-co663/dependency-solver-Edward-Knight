#!/usr/bin/env python3
"""Solves dependency issues for a package manager. See
https://github.com/ukc-co663/depsolver
"""
# Ubuntu 16.04 python3 is version 3.5.1-3
# https://packages.ubuntu.com/xenial/python3
import argparse
import bisect
import json
import pycosat
import re
import sys
import types

SAT_NUMBER = [None]


class Package(types.SimpleNamespace):
    """Container class representing a package.

    find_constraint_options must be called to populate conflicts and
    dependencies.
    """
    def __init__(self, package_data):
        self.name = package_data["name"]
        self.version = [int(part) for part in
                        package_data["version"].split(".")]
        self.size = package_data["size"]

        if "depends" in package_data:
            self.dependency_constraints = self.parse_dependency_constraints(
                package_data["depends"])
        else:
            self.dependency_constraints = []
        self.dependencies = None

        if "conflicts" in package_data:
            self.conflict_constraints = [
                Constraint(conflict_data)
                for conflict_data in package_data["conflicts"]
            ]
        else:
            self.conflict_constraints = []
        self.conflicts = None

        # register self as a number to be used in SAT solver
        global SAT_NUMBER
        SAT_NUMBER.append(self)
        self.sat_number = len(SAT_NUMBER) - 1

    def parse_dependency_constraints(self, dependency_data):
        """Parses a list of dependency data into a list of Constraint objects.
        """
        constraint_list = []
        for constraint_data in dependency_data:
            if isinstance(constraint_data, list):
                constraint_list.append(
                    self.parse_dependency_constraints(constraint_data))
            else:
                constraint_list.append(Constraint(constraint_data))
        return constraint_list

    def find_constraint_options(self, repository):
        """Uses the constraints and the repository to create self.conflicts
        (a dictionary mapping package names to a list of conflicting Package
        objects), and self.dependencies (a dictionary mapping package names to a
        list of possible required Package objects).

        Also rationalises the dependency lists to remove any packages that
        conflict.
        """
        # parse dependencies
        self.dependencies = []
        for constraint_list in self.dependency_constraints:
            depends = []
            for constraint in constraint_list:
                if constraint.name not in repository:
                    continue
                for package in repository[constraint.name]:
                    if constraint.fulfilled_by(package):
                        depends.append(package)
            if len(depends) != 0:
                self.dependencies.append(depends)

        # parse conflicts
        self.conflicts = []
        for constraint in self.conflict_constraints:
            if constraint.name not in repository:
                continue
            for package in repository[constraint.name]:
                if constraint.fulfilled_by(package):
                    self.conflicts.append(package)

        # rationalise dependency list (if a dependency is a conflict, remove it)
        for conflict in self.conflicts:
            for depends_list in self.dependencies:
                if conflict in depends_list:
                    depends_list.remove(conflict)

    def __str__(self):
        return self.name + "=" + ".".join(str(part) for part in self.version)

    def __repr__(self):
        # debug
        return str(self)


class Constraint(types.SimpleNamespace):
    # todo: docstring
    CONSTRAINT_REGEX = re.compile(
        r"(?P<name>[.+a-zA-Z0-9-]+)"
        r"((?P<constraint>(=|<|>|<=|>=))(?P<version>[0-9.]+))?")

    def __init__(self, constraint_data):
        match = self.CONSTRAINT_REGEX.match(constraint_data)
        if match is None:
            raise Exception("Constraint data invalid: "
                            + str(constraint_data))
        group_dict = match.groupdict()
        assert (group_dict["constraint"] is None) == (group_dict["version"] is None)

        self.name = group_dict["name"]
        self.constraint = group_dict["constraint"]
        self.version = group_dict["version"]
        if self.version is not None:
            self.version = [int(part) for part in
                            group_dict["version"].split(".")]

    def fulfilled_by(self, package):
        if self.name != package.name:
            return False
        if self.constraint is None and self.version is None:
            return True
        if self.constraint == "=":
            return package.version == self.version
        if self.constraint == "<":
            return package.version < self.version
        if self.constraint == ">":
            return package.version > self.version
        if self.constraint == "<=":
            return package.version <= self.version
        if self.constraint == ">=":
            return package.version >= self.version
        raise NotImplementedError("Constraint '" + str(self.constraint)
                                  + "' not recognised.")

    def __str__(self):
        result = self.name
        if self.constraint is not None and self.version is not None:
            result += self.constraint + ".".join(str(part) for part in
                                                     self.version)
        return result

    def __repr__(self):
        return self.__class__.__name__ + "(" + str(self) + ")"


def parse(repository_data, initial_data, constraints_data):
    # todo: docstring
    # parse repository_data
    repository = {}
    for package_data in repository_data:
        package = Package(package_data)
        if package.name in repository:
            repository[package.name].append(package)
        else:
            repository[package.name] = [package]
    for package_versions in repository.values():
        for package in package_versions:
            package.find_constraint_options(repository)

    # parse initial_data
    # assuming all installed packages are available in the repository
    initial = []
    for package_version in initial_data:
        constraint = Constraint(package_version)
        for package in repository[constraint.name]:
            if constraint.fulfilled_by(package):
                initial.append(package)
                break

    # parse constraints_data
    uninstall = []
    install = []
    for constraint_data in constraints_data:
        constraint = Constraint(constraint_data[1:])
        if constraint_data[0] == "-":
            assert constraint.name in repository
            for package in repository[constraint.name]:
                if constraint.fulfilled_by(package):
                    uninstall.append(package)
                    break
        else:
            install.append(constraint)

    return repository, initial, uninstall, install


def install_dependencies(repository, initial, uninstall, package):
    """Create the commands required to install the specified package including
    requirements. Selects dependencies based on their size.

    todo: include size of dependencies in calculation
    todo: look ahead to find conflicts instead of failing
    """
    commands = []
    for dependency_list in package.dependencies:
        smallest = None
        for possible_dependency in dependency_list:
            if possible_dependency in uninstall:
                continue
            for initial_package in initial:
                if possible_dependency in initial_package.conflicts:
                    break
            else:
                # package is not conflicting
                if smallest is None or possible_dependency.size < smallest.size:
                    smallest = possible_dependency
        if smallest is None:
            # need to uninstall another package so this one can be installed
            raise Exception("Failed to find package!")
        if smallest not in initial:
            initial.append(smallest)
            commands.extend(install_dependencies(repository, initial, uninstall,
                                                 smallest))
            commands.append("+" + str(smallest))
    return commands


def old_solve(repository, initial, uninstall, install):
    # naive implementation:
    # will fail instead of uninstalling a conflicting package
    commands = []

    for package in uninstall:
        if package in initial:
            commands.append("-" + str(package))
            initial.remove(package)

    for constraint in install:
        # todo: include size of dependencies in calculation
        smallest = None
        for potential_package in repository[constraint.name]:
            if potential_package in uninstall:
                continue
            if not constraint.fulfilled_by(potential_package):
                continue
            for initial_package in initial:
                if potential_package in initial_package.conflicts:
                    break
            else:
                # package is not conflicting
                if smallest is None or potential_package.size < smallest.size:
                    smallest = potential_package
        if smallest is None:
            # need to uninstall another package so this one can be installed
            raise Exception("Failed to find package!")
        if smallest in initial:
            continue
        initial.append(smallest)
        commands.extend(install_dependencies(repository, initial, uninstall,
                                             smallest))
        commands.append("+" + str(smallest))

    return commands


def toposort(nodes, count):
    output = []
    to_remove = []
    # initialise list of nodes with no incoming edges
    for node in nodes.keys():
        if count[node] == 0:
            to_remove.append(node)

    # create output list
    for _ in range(len(nodes)):
        if len(to_remove) == 0:
            raise Exception("Unable to toposort solution")
        node = to_remove.pop(0)
        output.append(node)
        for outgoing_node in nodes[node]:
            count[outgoing_node] -= 1
            if count[outgoing_node] == 0 and outgoing_node not in to_remove:
                bisect.insort(to_remove, outgoing_node)

    return output


def solve(repository, initial, uninstall, install):
    """Convert the problem to a SAT problem in CNF and run PicoSAT over it."""
    clauses = []
    # encode conflicts and dependencies of repository
    for package_versions in repository.values():
        for package in package_versions:
            # A conflicts B -> !A OR !B
            for conflict in package.conflicts:
                clauses.append([-package.sat_number, -conflict.sat_number])

            for dependency_list in package.dependencies:
                # A requires B or C -> !A OR B OR C
                sub_clause = [-package.sat_number]
                for possible_dependency in dependency_list:
                    sub_clause.append(possible_dependency.sat_number)
                clauses.append(sub_clause)

    # encode uninstall constraints
    for package in uninstall:
        clauses.append([-package.sat_number])

    # encode install constraints
    for constraint in install:
        sub_clause = []
        for package in repository[constraint.name]:
            if constraint.fulfilled_by(package):
                sub_clause.append(package.sat_number)
        clauses.append(sub_clause)

    # todo: allow uninstalling from initial state
    for package in initial:
        clauses.append([package.sat_number])

    # solve!
    result = pycosat.solve(clauses, vars=len(SAT_NUMBER) - 1)
    if isinstance(result, str):
        raise Exception(result)

    # convert SAT solution into lists of packages to install and uninstall
    to_install = []
    to_uninstall = []
    for sat_number in result:
        package = SAT_NUMBER[abs(sat_number)]
        if sat_number > 0:
            to_install.append(package)
        else:
            # uninstall
            to_uninstall.append(package)

    # rationalise to_install, taking initial state into account
    to_install = [p for p in to_install if p not in initial]
    # ("to_install:", *[p.sat_number for p in to_install])  # debug

    # ignore to_uninstall because we're not allowing uninstalls from initial state

    # sort the commands in the correct install order
    # build graph structure for toposort
    nodes = {p.sat_number: [] for p in to_install}
    count = {p.sat_number: 0 for p in to_install}
    for package in to_install:
        # add outgoing edges based on dependencies
        for dependency_list in package.dependencies:
            fulfilled = False
            for dependency in dependency_list:
                if dependency in initial:
                    # dependency fulfilled by initial
                    fulfilled = True
                    break
            if not fulfilled:
                # dependency not fulfilled by initial
                for dependency in dependency_list:
                    if dependency in to_install:
                        # dependency fulfilled by new install
                        # add edge to graph
                        nodes[dependency.sat_number].append(package.sat_number)
                        count[package.sat_number] += 1
                        fulfilled = True
                        break
            if not fulfilled:
                raise Exception("Unable to satisfy dependency for " + str(package))

    # toposort!
    # print("nodes:", nodes)  # debug
    to_install_sat_numbers = toposort(nodes, count)
    # print("to_install:", *to_install_sat_numbers)  # debug

    # convert to commands
    commands = ["+" + str(SAT_NUMBER[n]) for n in to_install_sat_numbers]

    return commands


def main():
    def json_from_file(file_path):
        """Helper method to read and parse a JSON file."""
        with open(file_path) as f:
            return json.load(f)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_data", type=json_from_file)
    parser.add_argument("initial_data", type=json_from_file)
    parser.add_argument("constraints_data", type=json_from_file)
    args = parser.parse_args()

    repository, initial, uninstall, install = parse(**args.__dict__)
    commands = solve(repository, initial, uninstall, install)

    json.dump(commands, sys.stdout)
    sys.stdout.flush()


if __name__ == "__main__":
    # sys.setrecursionlimit(100000)  # lol
    main()
