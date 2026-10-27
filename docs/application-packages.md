# Native application candidates

Application packaging uses the common first-party staging policy in
`tools/application/candidate_tree.py`. Platform adapters supply explicit application,
media, helper and runtime components. This policy does not build dependencies or
download runtimes.

The assembler reserves a new output directory, inventories its inputs, copies and
checks their bytes and executable modes, then publishes `contents` and an atomic
`candidate.json` receipt. Existing outputs are never adopted or replaced. Failure
removes only the newly reserved output. Component destinations cannot escape,
collide or overwrite an application's existing assets. Nested runtime components
are ordered after their application directory. Relative links must remain inside
their component; Windows components reject links.

The receipt records the source commit, native target, component inventories and
actual candidate files. It declares a development candidate, with release readiness
false. Local byte integrity does not authenticate a release or seal a mutable
filesystem against concurrent modification.

The staging policy is checked on all three native CI lanes:

```sh
python3 -m unittest discover -s tools/application/tests -v
```

These checks cover relocation, Unicode paths, unchanged inputs, existing user data,
contained links, partial copy failure and input mutation. They do not qualify an
installer, an application window or playback. Complete native adapters, runtime
closure, relocated launch, restart and interoperability acceptance remain required.
The developer JDK described in `tools/jvm/toolchains.json` is not an application
runtime input; Linux distribution requires a separately reviewed JVM package.
