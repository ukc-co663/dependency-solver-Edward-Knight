#!/usr/bin/env python3
"""Solves dependency issues for a package manager. See
https://github.com/ukc-co663/depsolver
"""
# Ubuntu 16.04 python3 is version 3.5.1-3
# https://packages.ubuntu.com/xenial/python3
import argparse
import json
import re
import sys
import types


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
            for constraint in constraint_list:
                depends = []
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
            conflicts = []
            if constraint.name not in repository:
                continue
            for package in repository[constraint.name]:
                if constraint.fulfilled_by(package):
                    conflicts.append(package)
            if len(conflicts) != 0:
                self.conflicts.append(conflicts)

        # rationalise dependency list (if a dependency is a conflict, remove it)
        for conflict_list in self.conflicts:
            for conflict in conflict_list:
                for depends_list in self.dependencies:
                    if conflict in depends_list:
                        depends_list.remove(conflict)

    def __str__(self):
        return self.name + "=" + ".".join(str(part) for part in self.version)


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
        name, version = package_version.split("=")
        for package in repository[name]:
            if package.version == version:
                initial.append(package)
                break

    # parse constraints_data
    uninstall = []
    install = []
    for constraint_data in constraints_data:
        constraint = Constraint(constraint_data[1:])
        if constraint_data[0] == "-":
            uninstall.append(constraint)
        else:
            install.append(constraint)

    return repository, initial, uninstall, install


def solve(repository, initial, uninstall, install):
    # naive implementation:
    # loosely checks initial state
    # does not update initial state
    # does not check version
    # does not check for dependencies
    # does not check for conflicts
    commands = []

    for constraint in uninstall:
        commands.append("-" + str(constraint))

    for constraint in install:
        package = repository[constraint.name][0]
        if package in initial:
            continue
        commands.append("+" + str(package))

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
    main()
