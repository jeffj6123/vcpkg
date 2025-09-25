
import subprocess
import re
import sys
import os
import shutil
import time

# This script generates .def files for DLLs to be used as forwarding DLLs.
# It uses the `dumpbin` tool to extract exported symbols from the DLLs,
# and then performs the following steps from here https://learn.microsoft.com/en-us/windows/arm/arm64x-build#building-an-arm64x-pure-forwarder-dll
# 1. Create an empty .cpp file.
# 2. Compile the empty .cpp file to create object files for both architectures.
# 3. Create .def files for both ARM64 and x64 architectures.
# 4. Create import libraries from the .def files.
# 5. Link the object files and import libraries to create the forwarding DLL.
# 6. If LNK1397 errors occur, update .def files with DATA and retry linking.

output_base_folder = "output"
dlls = [
    {
        "arm64_name": "libcurl",
        "arm64_package": r"C:\pkg_cache\Azure.Blob.Cpp.Client.SF.12.13.0\installed\arm64-windows\bin",
        "x64_name": None,
        "x64_package": r"C:\pkg_cache\Azure.Blob.Cpp.Client.SF.12.13.0\installed\x64-windows\bin",
    },
    {
        "arm64_name": "libcrypto-3-arm64",
        "arm64_package": r"C:\pkg_cache\Microsoft.Internal.ServiceFabric.grpc-arm64.2.5.0\bin",
        "x64_name": "libcrypto-3-x64",
        "x64_package": r"C:\pkg_cache\Microsoft.Internal.ServiceFabric.grpc-x64.2.5.0\bin",
    },
    {
        "arm64_name": "libssl-3-arm64",
        "arm64_package": r"C:\pkg_cache\Microsoft.Internal.ServiceFabric.grpc-arm64.2.5.0\bin",
        "x64_name": "libssl-3-x64",
        "x64_package": r"C:\pkg_cache\Microsoft.Internal.ServiceFabric.grpc-x64.2.5.0\bin",
    },
    {
        "arm64_name": "re2",
        "arm64_package": r"C:\pkg_cache\Microsoft.Internal.ServiceFabric.grpc-arm64.2.5.0\bin",
        "x64_name": None,
        "x64_package": r"C:\pkg_cache\Microsoft.Internal.ServiceFabric.grpc-x64.2.5.0\bin",
    },
    {
        "arm64_name": "zlib1",
        "arm64_package": r"C:\pkg_cache\Microsoft.Internal.ServiceFabric.grpc-arm64.2.5.0\bin",
        "x64_name": None,
        "x64_package": r"C:\pkg_cache\Microsoft.Internal.ServiceFabric.grpc-x64.2.5.0\bin",
    },
    {
        "arm64_name": "ManagedCertStore",
        "arm64_package": r"C:\pkg_cache\DsmsCredentialsManagement.arm64.3.20.59\lib\Native",
        "x64_name": None,
        "x64_package": r"C:\pkg_cache\DsmsCredentialsManagement.3.20.59\lib\Native",
    },
    {
        "arm64_name": "SecretsPackage",
        "arm64_package": r"C:\pkg_cache\DsmsCredentialsManagement.arm64.3.20.59\lib\Native",
        "x64_name": None,
        "x64_package": r"C:\pkg_cache\DsmsCredentialsManagement.3.20.59\lib\Native",
    },
]

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

def write_def_file(symbols, forward_to_dll, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("EXPORTS\n")
        for symbol in symbols:
            f.write(f"    {symbol} = {forward_to_dll}.{symbol}\n")
    print(f"Annotated .def file written to {output_path}")

def run_command(cmd, cwd):
    print(f"Running in {cwd}:\n  {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(f"Output:\n{result.stdout}")
    except subprocess.CalledProcessError as e:
        print(f"Command failed with return code {e.returncode}")
        print(f"Standard Output:\n{e.stdout}")
        print(f"Error Output:\n{e.stderr}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def create_empty_obj(source_path):
    with open(source_path, "w") as f:
        f.write("")

def compile_empty_obj(source_path, output_obj, cwd, arch=None):
    cmd = ["cl", "/c", f"/Fo{output_obj}"]
    if arch == "arm64EC":
        cmd.append("/arm64EC")
    cmd.append(source_path)
    run_command(cmd, cwd)

def create_import_lib(def_file, output_lib, machine, cwd):
    cmd = [
        "link", "/lib",
        f"/machine:{machine}",
        f"/def:{def_file}",
        f"/out:{output_lib}"
    ]
    run_command(cmd, cwd)

def update_def_files(symbol, def_files):
    for def_file in def_files:
        if not os.path.exists(def_file):
            print(f"❌ File not found: {def_file}")
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
            print(f"✅ Updated {def_file} with DATA for symbol: {symbol}")
        else:
            print(f"ℹ️ Symbol {symbol} already marked or not found in {def_file}")

def link_forwarder_dll(output_dll, arm64_def, x64_def, arm64_obj, x64_obj, arm64_lib, x64_lib, cwd):
    cmd = [
        "link", "/dll", "/noentry",
        f"/out:{output_dll}",
        "/machine:arm64x",
        f"/defArm64Native:{arm64_def}",
        f"/def:{x64_def}",
        arm64_obj, x64_obj,
        arm64_lib, x64_lib,
    ]
    symbol_pattern = re.compile(r"LNK1397: '([^']+)' is an invalid name")
    attempt = 1
    while True:
        print(f"\n Attempt #{attempt}: Running link.exe...")
        try:
            result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()

            if result.returncode == 0:
                print("link.exe succeeded.")
                break

            print("⚠️ link.exe stderr output:")
            print(stderr)
            print("📄 link.exe stdout output:")
            print(stdout)

            match = symbol_pattern.search(stderr) or symbol_pattern.search(stdout)
            if match:
                symbol = match.group(1)
                print(f"🔍 Detected invalid export symbol: {symbol}")
                update_def_files(symbol, [os.path.join(cwd, arm64_def), os.path.join(cwd, x64_def)])
                time.sleep(1)
                attempt += 1
            else:
                print("No LNK1397 symbol found. Check the error above.")
                break
        except Exception as e:
            print(f"Exception occurred: {e}")
            break

def create_forwarding_dll(folder_path, dll_name):
    empty_obj_path = os.path.join(folder_path, "empty.cpp")
    create_empty_obj(empty_obj_path)
    compile_empty_obj("empty.cpp", "empty_arm64.obj", cwd=folder_path)
    compile_empty_obj("empty.cpp", "empty_x64.obj", cwd=folder_path, arch="arm64EC")

    create_import_lib("x64.def", "x64.lib", machine="x64", cwd=folder_path)
    create_import_lib("arm64.def", "arm64.lib", machine="arm64", cwd=folder_path)

    link_forwarder_dll(
        f"{dll_name}.dll",
        "arm64.def", "x64.def",
        "empty_arm64.obj", "empty_x64.obj",
        "arm64.lib", "x64.lib",
        cwd=folder_path
    )

    is_arm64x = is_arm64x_dll(os.path.join(folder_path, f"{dll_name}.dll"))
    if is_arm64x:
        print(f"{dll_name}.dll is ARM64X architecture.")
    else:
        print(f"{dll_name}.dll is not ARM64X architecture.")

def create_folder(package_name):
    folder_name = package_name.replace(" ", "_").lower()
    if not os.path.exists(output_base_folder):
        os.makedirs(output_base_folder)
    folder_name = os.path.join(output_base_folder, folder_name)
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
    return folder_name

def generate_def_files(arm64_package_name, x64_package_name, arm64_dll_name, x64_dll_name):
    print(f"all info {arm64_package_name}, {x64_package_name}, {arm64_dll_name}, {x64_dll_name}")    
    folder_path = create_folder(arm64_dll_name)
    generate_def_file(arm64_package_name, arm64_dll_name, "arm64", folder_path)
    generate_def_file(x64_package_name, x64_dll_name, "x64", folder_path)
    return folder_path

def generate_def_file(package_name, dll_name, architecture, output_folder):
    def_file_path = os.path.join(output_folder, architecture + ".def")
    dll_path = os.path.join(package_name, f"{dll_name}.dll")
    dumpbin_output = extract_exports(dll_path)
    symbols = parse_exports(dumpbin_output)
    write_def_file(symbols, dll_name + "_" + architecture, def_file_path)

def is_arm64x_dll(dll_path):
    try:
        result = subprocess.run(
            ["dumpbin", "/headers", dll_path],
            capture_output=True,
            text=True,
            check=True
        )
        for line in result.stdout.splitlines():
            if "machine" in line.lower() and "ARM64X" in line:
                return True
        return False
    except subprocess.CalledProcessError as e:
        print(f"Error checking file header: {e}")
        return False

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

def copy_dll_files(source_dir, destination_dir):
    if not os.path.exists(destination_dir):
        os.makedirs(destination_dir)
    for root, _, files in os.walk(source_dir):
        for file in files:
            if file.lower().endswith('.dll'):
                source_file = os.path.join(root, file)
                destination_file = os.path.join(destination_dir, file)
                try:
                    shutil.copy2(source_file, destination_file)
                    print(f"Copied: {source_file} -> {destination_file}")
                except Exception as e:
                    print(f"Failed to copy {source_file}: {e}")

if __name__ == "__main__":
    for dll_info in dlls:
        arm_64_name = dll_info.get("arm64_name", None)
        x64_name = dll_info.get("x64_name", arm_64_name)
        if x64_name is None:
            x64_name = arm_64_name
        folder_name = generate_def_files(dll_info["arm64_package"], dll_info["x64_package"],
                                         arm_64_name, x64_name)
        print(f"Creating forwarding DLL for {arm_64_name} and {x64_name} in folder: {folder_name}")
        create_forwarding_dll(folder_name, arm_64_name)
    copy_dll_files(os.getcwd(), "forwarding_dlls")
