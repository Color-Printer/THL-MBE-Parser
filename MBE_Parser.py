import os
import sys
import struct
import csv

COLUMN_TYPES = {
    0x2: {'name': 'Int',      'size': 4, 'format': '<i'},
    0x9: {'name': 'Bool',     'size': 4, 'format': '=?3x'},
    0x4: {'name': 'Byte',     'size': 1, 'format': '<b'},
    0x5: {'name': 'Float',    'size': 4, 'format': '<f'},
    0x7: {'name': 'String',   'size': 8, 'format': '<q'},
    0x8: {'name': 'StringID', 'size': 8, 'format': '<q'},
    0x3: {'name': 'ShortInt', 'size': 2, 'format': '<h'},
}

def read_string_with_padding(f, size):
    """Reads a string of a fixed length and removes the null padding."""
    if size <= 0:
        return ""
    raw_bytes = f.read(size)
    return raw_bytes.decode('utf-8', errors='ignore').rstrip('\x00')

def align_offset(offset, alignment):
    """Calculates the next offset that is a multiple of the required alignment."""
    return (offset + alignment - 1) & ~(alignment - 1)

def parse_mbe(filepath):
    """
    Parses an .MBE file, handling all rules for padding and alignment.
    """
    try:
        with open(filepath, 'rb') as f:
            # 1. MBE File Header
            magic_number = f.read(4)
            if magic_number != b'EXPA':
                raise ValueError("Magic Number 'EXPA' not found. The file is not a valid MBE.")
            
            num_expa_regions, = struct.unpack('<i', f.read(4))
            print(f"MBE file detected. Contains {num_expa_regions} sheets (EXPA Regions).")

            all_sheets_data = []
            string_location_map = {}

            # 2. Loop through EXPA regions (Individual sheets)
            for sheet_idx in range(num_expa_regions):
                print(f"\n--- Analyzing Sheet #{sheet_idx+1}/{num_expa_regions} ---")
                
                # Ensures that EVERY EXPA table starts at an offset divisible by 8.
                # This padding (usually bytes reading 0xCC) occurs BETWEEN tables.
                current_pos = f.tell()
                padding_needed = (8 - (current_pos % 8)) % 8
                if padding_needed > 0:
                    f.read(padding_needed)
                        
                # 2.1 EXPA Header Processing
                sheet_name_size, = struct.unpack('<i', f.read(4))
                sheet_name = read_string_with_padding(f, sheet_name_size)
                
                num_columns, = struct.unpack('<i', f.read(4))
                column_type_codes = struct.unpack(f'<{num_columns}i', f.read(4 * num_columns))
                columns = [COLUMN_TYPES[code] for code in column_type_codes]
                column_headers = [f"{col['name']}_{idx}" for idx, col in enumerate(columns)]
                
                expa_area_size, = struct.unpack('<i', f.read(4))
                num_expa_areas, = struct.unpack('<i', f.read(4))

                print(f"Sheet Name: '{sheet_name}'")
                print(f"Columns: {num_columns}, Lines: {num_expa_areas}, Line Size: {expa_area_size} bytes")

                # 2.2 Lines in EXPA region
                sheet_rows = []
                for row_idx in range(num_expa_areas):
                    # Ensures that EVERY EXPA line starts at an offset divisible by 8.
                    # This padding (usually bytes reading 0xCC) occurs BETWEEN lines.
                    current_pos = f.tell()
                    padding_needed = (8 - (current_pos % 8)) % 8
                    if padding_needed > 0:
                        f.read(padding_needed) # Discard the padding bytes

                    row_start_offset_in_file = f.tell()
                    row_data_bytes = f.read(expa_area_size)
                    
                    parsed_row = []
                    current_offset_in_row = 0

                    for col_idx, col_info in enumerate(columns):
                        if col_info['size'] == None:
                            alignment = 4
                        else:
                            alignment = col_info['size']
                        
                        current_offset_in_row = align_offset(current_offset_in_row, alignment)
                        
                        if col_info['name'] in ('String', 'StringID'):
                            absolute_file_offset = row_start_offset_in_file + current_offset_in_row
                            string_location_map[absolute_file_offset] = (sheet_idx, row_idx, col_idx)
                            parsed_row.append('') # Placeholder
                        else:
                            value_bytes = row_data_bytes[current_offset_in_row : current_offset_in_row + col_info['size']]
                            value, = struct.unpack(col_info['format'], value_bytes)
                            parsed_row.append(value)
                        
                        current_offset_in_row += col_info['size']
                    
                    sheet_rows.append(parsed_row)
                
                all_sheets_data.append({
                    'name': sheet_name, 'columns': columns,
                    'headers': column_headers, 'rows': sheet_rows
                })

            # Alignment for the CHNK Section
            current_pos = f.tell()
            padding_needed = (8 - (current_pos % 8)) % 8
            if padding_needed > 0:
                print(f"\nAligning the CHNK Section to 8 Bytes. Skipping {padding_needed} padding bytes.")
                f.read(padding_needed)

            # 3. CHNK Section (for Strings)
            chnk_magic = f.read(4)
            if chnk_magic != b'CHNK':
                print("\nWarning: 'CHNK' section not found after EXPA regions.")
            else:
                num_strings, = struct.unpack('<i', f.read(4))
                print(f"\n--- Analyzing the CHNK section for strings ---")
                print(f"Found {num_strings} strings for processing.")
                
                for _ in range(num_strings):
                    symbolic_offset, = struct.unpack('<i', f.read(4))
                    string_size, = struct.unpack('<i', f.read(4))
                    string_value = read_string_with_padding(f, string_size)
                    
                    location = string_location_map.get(symbolic_offset)
                    if location:
                        sheet_idx, row_idx, col_idx = location
                        all_sheets_data[sheet_idx]['rows'][row_idx][col_idx] = string_value
                    else:
                        print(f"Warning: The string '{string_value}' with symbolic offset {symbolic_offset} does not correspond to any mapped location in the EXPA section.")

            return all_sheets_data

    except FileNotFoundError:
        print(f"Error: The file '{filepath}' was not found.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during parsing: {e}")
        import traceback
        traceback.print_exc()
        print("Attempting dump of existing sheets...")
        return all_sheets_data

def create_csv_files(output_dir, sheets_data):
    if not sheets_data:
        print("No CSV data detected.")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"\nDirectory '{output_dir}' created.")

    print("\n--- Generating CSV Files ---")
    # Iterate using `enumerate` to get the sheet index.
    for idx, sheet in enumerate(sheets_data):
        safe_sheet_name = "".join(c for c in sheet['name'] if c.isalnum() or c in (' ', '_', '-')).rstrip()
        # Adds the numeric prefix to the file name
        csv_filename = f"{output_dir}\{idx}_{safe_sheet_name}.csv"
        csv_filepath = csv_filename

        try:
            with open(csv_filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(sheet['headers'])
                writer.writerows(sheet['rows'])
            
            print(f"CSV '{csv_filepath}' successfully created.")

        except IOError as e:
            print(f"Error writing CSV file '{csv_filepath}': {e}")

def main():
    if len(sys.argv) != 2:
        print("Usage: python MBE_Parser.py <filepath.mbe>")
        sys.exit(1)

    input_filepath = sys.argv[1]
    output_dir = os.path.splitext(os.path.basename(input_filepath))[0]

    print(f"Processing file: {input_filepath}")
    
    sheets_data = parse_mbe(input_filepath)

    if sheets_data:
        create_csv_files(output_dir, sheets_data)
        print("\nProcess complete!")

if __name__ == "__main__":
    main()