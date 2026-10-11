import os
import sys
import struct
import csv
from io import BytesIO

COLUMN_INFO_BY_NAME = {
    'Int':      {'name': 'Int', 'code': 0x2, 'size': 4, 'format': '<i'},
    'Bool':     {'name': 'Bool', 'code': 0x9, 'size': 4, 'format': '=?3x'},
    'Byte':     {'name': 'Byte', 'code': 0x4, 'size': 1, 'format': '<b'},
    'Float':    {'name': 'Float', 'code': 0x5, 'size': 4, 'format': '<f'},
    'String':   {'name': 'String', 'code': 0x7, 'size': 8, 'format': '<q'},
    'StringID': {'name': 'StringID', 'code': 0x8, 'size': 8, 'format': '<q'},
    'ShortInt': {'name': 'ShortInt', 'code': 0x3, 'size': 2, 'format': '<h'},
}

def write_padded_string(f, text):
    """Writes a string padded to aligned to a multiple of 4 bytes."""
    if not text:
        data = b'\x00\x00\x00\x00'
    else:
        encoded_data = text.encode('utf-8') + b'\x00\x00'
        padded_size = (len(encoded_data) + 3) & ~3
        data = encoded_data.ljust(padded_size, b'\x00')
    
    f.write(data)
    return len(data)

def write_alignment_padding(f, alignment, pad_byte=b'\x00'):
    """Writes padding bytes to align the current file position."""
    current_pos = f.tell()
    padding_needed = (alignment - (current_pos % alignment)) % alignment
    if padding_needed > 0:
        f.write(pad_byte * padding_needed)

def calculate_expa_area_size(columns):
    """Calculates the size of an EXPA area (row) in bytes."""
    size = 0
    for col_info in columns:
        if col_info['size'] == None:
            alignment = 4
        else:
            alignment = col_info['size']
        size = (size + alignment - 1) & ~(alignment - 1)
        size += col_info['size']
    return (size + 7) & ~(7)

def repack_mbe(input_dir, output_filepath):
    print(f"Repacking the folder '{input_dir}' into MBE file '{output_filepath}'")
    
    try:
        csv_files = sorted(
            [f for f in os.listdir(input_dir) if f.endswith('.csv')],
            key=lambda f: int(f.split('_')[0])
        )
    except (ValueError, IndexError):
        print("Error: The CSV files in the folder are not in the format '0_name.csv', '1_name.csv', etc.\n(This packer only works well with MBE files unpacked with MBE_Parser.py.)")
        return

    if not csv_files:
        print("No CSV files found in folder.")
        return

    print(f"Files found and sorted: {csv_files}")

    all_sheets_data = []
    chnk_strings_to_write = []

    for filename in csv_files:
        sheet_name = '_'.join(filename.split('_')[1:]).replace('.csv', '')
        sheet = {'name': sheet_name, 'rows': [], 'columns': []}
        
        with open(os.path.join(input_dir, filename), 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            headers = next(reader)
            
            for header in headers:
                col_type_name = header.split('_')[0]
                sheet['columns'].append(COLUMN_INFO_BY_NAME[col_type_name])
            
            for row in reader:
                sheet['rows'].append(row)

        all_sheets_data.append(sheet)

    with open(output_filepath, 'wb') as f:
        f.write(b'EXPA')
        f.write(struct.pack('<i', len(all_sheets_data)))

        for sheet in all_sheets_data:
            print(f"\n--- Packing sheet: {sheet['name']} ---")
            
            write_alignment_padding(f, 8, b'\xcc')
            
            with BytesIO() as temp_buffer:
                sheet_name_padded_size = write_padded_string(temp_buffer, sheet['name'])
                padded_sheet_name_bytes = temp_buffer.getvalue()

            f.write(struct.pack('<i', sheet_name_padded_size))
            f.write(padded_sheet_name_bytes)

            f.write(struct.pack('<i', len(sheet['columns'])))
            
            column_codes = [col['code'] for col in sheet['columns']]
            f.write(struct.pack(f'<{len(column_codes)}i', *column_codes))

            expa_area_size = calculate_expa_area_size(sheet['columns'])
            f.write(struct.pack('<i', expa_area_size))
            f.write(struct.pack('<i', len(sheet['rows'])))
            print(f"Calculated line size: {expa_area_size} bytes")

            for row_idx, row_data in enumerate(sheet['rows']):
                write_alignment_padding(f, 8, b'\xcc')
                row_start_offset = f.tell()
                
                # **** PADDING CORRECTION ****
                with BytesIO() as row_buffer:
                    for col_idx, value_str in enumerate(row_data):
                        col_info = sheet['columns'][col_idx]
                        
                        if col_info['size'] == None:
                            align = 4
                        else:
                            align = col_info['size']
                        
                        current_pos_in_row = row_buffer.tell()
                        padding_needed = (align - (current_pos_in_row % align)) % align
                        row_buffer.write(b'\x00' * padding_needed)

                        if col_info['name'] in ('String', 'StringID'):
                            symbolic_offset = row_start_offset + row_buffer.tell()
                            if value_str:
                                chnk_strings_to_write.append((symbolic_offset, value_str))
                            row_buffer.write(b'\x00' * 8)
                        else:
                            value = 0 # Default value
                            if value_str: # Handle empty cells in CSV
                                if col_info['name'] in ('Int', 'Byte', 'ShortInt'):
                                    value = int(value_str)
                                elif col_info['name'] == 'Float':
                                    value = float(value_str)
                                elif col_info['name'] == 'Bool':
                                    if value_str in ('True', 'true', '1'):
                                        value = 1
                                    else:
                                        value = 0
                            
                            row_buffer.write(struct.pack(col_info['format'], value))
                    
                    final_row_bytes = row_buffer.getvalue()
                
                # Writes the bytes that were read while the buffer was open
                f.write(final_row_bytes)
                padding_to_fill_area = expa_area_size - len(final_row_bytes)
                if padding_to_fill_area > 0:
                    f.write(b'\x00' * padding_to_fill_area)

        write_alignment_padding(f, 8, b'\x00')
        
        f.write(b'CHNK')
        f.write(struct.pack('<i', len(chnk_strings_to_write)))
        print(f"\n--- Packing the CHNK Section with {len(chnk_strings_to_write)} strings ---")

        for symbolic_offset, text in chnk_strings_to_write:
            f.write(struct.pack('<i', symbolic_offset))
            
            with BytesIO() as temp_buffer:
                string_padded_size = write_padded_string(temp_buffer, text)
                padded_string_bytes = temp_buffer.getvalue()

            f.write(struct.pack('<i', string_padded_size))
            f.write(padded_string_bytes)
    
    print(f"\nRepack completed. The MBE file '{output_filepath}' was successfully created.")


def main():
    if len(sys.argv) != 2:
        print("Usage: python MBE_Repacker.py <MBE_directory_filepath>")
        sys.exit(1)

    input_dir = sys.argv[1]
    if not os.path.isdir(input_dir):
        print(f"Error: The path '{input_dir}' is not a valid folder.")
        sys.exit(1)
        
    output_filename = os.path.basename(os.path.normpath(input_dir)) + ".mbe"
    output_filepath = os.path.join(os.path.dirname(input_dir), output_filename)

    repack_mbe(input_dir, output_filepath)


if __name__ == "__main__":
    main()