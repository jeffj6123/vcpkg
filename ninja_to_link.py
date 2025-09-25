import subprocess
import re
import time
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

# Generates protobuf arm64X dlls
# currently this should work just 

#if calling from another location that VCPKG set this to that directory
vcpkg_base_location = r""
vcpkg_packages_location = os.path.join(vcpkg_base_location, "packages")
vcpkg_buildtrees_location = os.path.join(vcpkg_base_location, "buildtrees")

arm64_ninja_log =  os.path.join(vcpkg_buildtrees_location, r"protobuf\config-arm64-windows-rel-ninja.log")
arm64ec_ninja_log = os.path.join(vcpkg_buildtrees_location, r"protobuf\config-arm64ec-windows-rel-ninja.log")

package_base = {
    "arm64_package_location": os.path.join(vcpkg_packages_location, r"protobuf_arm64-windows\bin"),
    "arm64_base": os.path.join(vcpkg_buildtrees_location, r"protobuf\arm64-windows-rel"),
    "arm64ec_package_location": os.path.join(vcpkg_packages_location, r"protobuf_arm64ec-windows\bin"),
    "arm64ec_base": os.path.join(vcpkg_buildtrees_location, r"protobuf\arm64ec-windows-rel"),
    "arm64_ninja_log": arm64_ninja_log,
    "arm64ec_ninja_log": arm64ec_ninja_log
}

packages = [
    # {
    #     "library_name": "libprotobuf-lite",
    #     **package_base
    # },
    # {
    #     "library_name": "libprotobuf",
    #     **package_base
    # },
    # {
    #     "library_name": "libprotoc",
    #     **package_base
    # },
    {
        "library_name": "re2",
        "arm64_package_location": os.path.join(vcpkg_packages_location, r"re2_arm64-windows\bin"),
        "arm64_base": os.path.join(vcpkg_buildtrees_location, r"re2\arm64-windows-rel"),
        "arm64ec_package_location": os.path.join(vcpkg_packages_location, r"re2_arm64ec-windows\bin"),
        "arm64ec_base": os.path.join(vcpkg_buildtrees_location, r"re2\arm64ec-windows-rel"),
        "arm64_ninja_log": os.path.join(vcpkg_buildtrees_location, r"re2\config-arm64-windows-rel-ninja.log"),
        "arm64ec_ninja_log": os.path.join(vcpkg_buildtrees_location, r"re2\config-arm64ec-windows-rel-ninja.log")
    },
    # {
    #     "library_name": "zlib1",
    #     "cmake_parse_name": "zlib",
    #     "arm64_package_location": os.path.join(vcpkg_packages_location, r"zlib_arm64-windows\bin"),
    #     "arm64_base": os.path.join(vcpkg_buildtrees_location, r"zlib\arm64-windows-rel"),
    #     "arm64ec_package_location": os.path.join(vcpkg_packages_location, r"zlib_arm64ec-windows\bin"),
    #     "arm64ec_base": os.path.join(vcpkg_buildtrees_location, r"zlib\arm64ec-windows-rel"),
    #     "arm64_ninja_log": os.path.join(vcpkg_buildtrees_location, r"zlib\config-arm64-windows-rel-ninja.log"),
    #     "arm64ec_ninja_log": os.path.join(vcpkg_buildtrees_location, r"zlib\config-arm64ec-windows-rel-ninja.log")
    # }
]

def extract_block(file_path, target_name):
    with open(file_path, 'r') as file:
        content = file.read()

    # Define the start and end markers for the block
    start_marker = f"# Link the shared library {target_name}.dll"
    build_line_pattern = rf"^build {re.escape(target_name)}\.dll.*$"

    end_marker = "# ============================================================================="

    # Find the start of the block
    start_index = content.find(start_marker)
    if start_index == -1:
        print(f"Start marker not found. {start_marker}")
        return

    # Find the end of the block
    end_index = content.find(end_marker, start_index)
    if end_index == -1:
        print("End marker not found.")
        return

    # Extract the block
    block = content[start_index:end_index + len(end_marker)]

    # Check if the build line is present in the block
    if not re.search(build_line_pattern, block, re.MULTILINE):
        print("Build line not found in the block.")
        return

    print("Extracted Block:\n")
    # print(block)
    return block

symbol_pattern = re.compile(r"LNK1397: '([^']+)' is an invalid name")

def extract_exports(dll_path):
    try:
        result = subprocess.run(
            ["dumpbin", "/exports", dll_path],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print("Error running dumpbin:", e)
        sys.exit(1)

def generate_def_file(package_name, dll_name, architecture, output_folder = ""):
    def_file_path = os.path.join(output_folder, architecture + ".def")
    print(def_file_path)
    dll_path = os.path.join(package_name, f"{dll_name}.dll")
    dumpbin_output = extract_exports(dll_path)
    symbols = parse_exports(dumpbin_output)

    return write_def_file(symbols, def_file_path)

def parse_exports(dumpbin_output):
    exports = []
    parsing = False
    for line in dumpbin_output.splitlines():
        if re.match(r"\s*ordinal\s+hint\s+RVA\s+name", line):
            parsing = True
            continue
        if parsing:
            match = re.match(r"\s*\d+\s+\w+\s+\w+\s+(\S+)", line)
            if match:
                symbol = match.group(1)
                exports.append(symbol)
    return exports

def write_def_file(symbols, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("EXPORTS\n")
        for symbol in symbols:
            f.write(f"    {symbol}\n")
    print(f"Annotated .def file written to {output_path}")
    return output_path

def update_def_files(symbol, def_files):
    for def_file in def_files:
        if not os.path.exists(def_file):
            print(f"File not found: {def_file}")
            continue
        with open(def_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        updated = False
        with open(def_file, 'w', encoding='utf-8') as f:
            for line in lines:
                if symbol in line and 'DATA' not in line:
                    f.write(line.strip() + ' DATA\n')
                    updated = True
                else:
                    f.write(line)
        if updated:
            print(f"Updated {def_file} with DATA for symbol: {symbol}")
        else:
            print(f"ℹ️ Symbol {symbol} already marked or not found in {def_file}")

def run_link_until_success(link_command, def_files):
    attempt = 1
    while True:
        print(f"\n Attempt #{attempt}: Running link.exe...")
        try:
            result = subprocess.run(link_command, capture_output=True, text=True)
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()

            if result.returncode == 0:
                print(" link.exe succeeded.")
                break

            print("link.exe stderr output:")
            print(stderr)
            print("link.exe stdout output:")
            print(stdout)

            match = symbol_pattern.search(stderr) or symbol_pattern.search(stdout)
            if match:
                symbol = match.group(1)
                print(f" Detected invalid export symbol: {symbol}")
                update_def_files(symbol, def_files)
                time.sleep(1)
                attempt += 1
            else:
                print(" No LNK1397 symbol found. Check the error above.")
                break
        except Exception as e:
            print(f" Exception occurred: {e}")
            break


def extract_value(pattern, text):
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""

# def parse_ninja_cmake(library_name, cmake_text, obj_base, include_resource_pattern=False):
#     # Extract object files and resource file

#     # Use raw string formatting to build regex patterns dynamically
#     obj_pattern = rf'CMakeFiles\\{re.escape(library_name)}\.dir\\[^\s|]+\.obj'
#     resource_pattern = rf'CMakeFiles\\{re.escape(library_name)}\.dir\\version\.rc\.res'

#     # Extract object files
#     obj_files = re.findall(obj_pattern, cmake_text)

#     # Include resource file if present
#     resource_file = re.search(resource_pattern, cmake_text)
#     if resource_file and include_resource_pattern:
#         obj_files.append(resource_file.group())

#     libraries = extract_value(r'LINK_LIBRARIES\s*=\s*(.+)', cmake_text)
    
#     annotate_local_libraries = ['libprotobuf.lib']

#     filtered_libraries = []
#     for library in libraries.split():
#         if library in annotate_local_libraries:
#             filtered_libraries.append(f"{obj_base}\\{library}")
#         else:
#             filtered_libraries.append(library)

#     cleaned_obj_files = []
#     for obj in obj_files:
#         cleaned = re.sub(r'\\\.\\', r'\\', obj)
#         cleaned_obj_files.append(cleaned)

#     ignore_flags = ["/machine:ARM64", "/machine:ARM64EC"]
#     link_flags_raw = extract_value(r'LINK_FLAGS\s*=\s*(.+)', cmake_text)
#     link_flags_filtered = []
#     for flag in link_flags_raw.split():
#         if flag in ignore_flags:
#             continue
#         if flag.startswith("-Wl"):
#             continue
#         # Add other filtering conditions here if needed
#         link_flags_filtered.append(flag)

#     command = f"{'\n' + obj_base + "\\" + ('\n' + obj_base + "\\").join(cleaned_obj_files)} {'\n'.join(link_flags_filtered)} {'\n'.join(filtered_libraries)}"
#     return command

import re

def extract_value(pattern, text):
    match = re.search(pattern, text)
    return match.group(1) if match else ""

def parse_ninja_cmake(library_name, cmake_text, obj_base, include_resource_pattern=False):
    # Extract object files from the build line
    obj_files = re.findall(r'CMakeFiles\\' + re.escape(library_name) + r'\.dir\\[^\s|]+\.obj', cmake_text)

    # Optionally include resource file
    resource_pattern = rf'CMakeFiles\\{re.escape(library_name)}\.dir\\version\.rc\.res'
    resource_file = re.search(resource_pattern, cmake_text)
    if resource_file and include_resource_pattern:
        obj_files.append(resource_file.group())

    # Clean up object file paths
    ignore_objs = ['exports.def.obj']
    cleaned_obj_files = []
    for obj in obj_files:
        can_include = True
        cleaned = re.sub(r'\\\.\\', r'\\', obj)
        for ignore_obj in ignore_objs:
            if cleaned.endswith(ignore_obj):
                can_include = False
        if can_include:
            cleaned_obj_files.append(cleaned)

    # Extract and filter link libraries
    libraries = extract_value(r'LINK_LIBRARIES\s*=\s*(.+)', cmake_text)

    print(libraries)
    annotate_local_libraries = ['libprotobuf.lib']
    filtered_libraries = [
        f"{obj_base}\\{lib}" if lib in annotate_local_libraries else lib
        for lib in libraries.split()
    ]


    crt_libs = ["msvcrt.lib", "msvcprt.lib", "vcruntime.lib", "ucrt.lib"]
    filtered_libraries.extend(crt_libs)


    # Extract and filter link flags
    ignore_flags = ["/machine:ARM64", "/machine:ARM64EC"]
    link_flags_raw = extract_value(r'LINK_FLAGS\s*=\s*(.+)', cmake_text)
    link_flags_filtered = [
        flag for flag in link_flags_raw.split()
        if flag not in ignore_flags and not flag.startswith("-Wl") and not flag.startswith("/DEF:")
    ]

    # Construct the final command
    command = f"{'\n' + obj_base + '\\' + ('\n' + obj_base + '\\').join(cleaned_obj_files)} {'\n'.join(link_flags_filtered)} {'\n'.join(filtered_libraries)}"
    return command

def recreate_directory(path):
    import shutil
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path)


def get_link_command(package):
    library_name = package['library_name']

    cmake_parse_name = library_name
    if "cmake_parse_name" in package:
        cmake_parse_name = package["cmake_parse_name"]

    arm64_cmake = extract_block(package["arm64_ninja_log"], library_name)
    arm64ec_cmake = extract_block(package["arm64ec_ninja_log"], library_name)

    arm64 = parse_ninja_cmake(cmake_parse_name, arm64_cmake, package['arm64_base'], True)
    arm64ec = parse_ninja_cmake(cmake_parse_name, arm64ec_cmake, package['arm64ec_base'])

    package_directory = os.path.join(os.getcwd(), library_name)
    recreate_directory(package_directory)

    arm64_def = generate_def_file(package['arm64_package_location'], library_name, "arm64", package_directory)
    arm64ec_def = generate_def_file(package['arm64ec_package_location'], library_name, "arm64ec", package_directory)
    
    out = os.path.join(package_directory, library_name + ".dll")
    imp_lib = os.path.join(package_directory, library_name + ".lib")
    pdb_lib = os.path.join(package_directory, library_name + ".pdb")

    rsp_file = f"""
{arm64}
{arm64ec}
/DLL
/OUT:{out}
/IMPLIB:{imp_lib}
/PDB:{pdb_lib}
/DEFARM64NATIVE:{arm64ec_def}
/DEF:{arm64_def}
/machine:ARM64X
/VERBOSE:LIB"""

    rsp_location =  os.path.join(package_directory, library_name + ".rsp")

    with open(rsp_location, "w") as out:
        out.write(rsp_file + "\n")
    
    link_command = ["link.exe", "@" + rsp_location]
    run_link_until_success(link_command, [arm64_def, arm64ec_def])
    return rsp_file

for package in packages:
    get_link_command(package)