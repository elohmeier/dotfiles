function compress-video --description "Compress video using HEVC with optimized settings"
    if test (count $argv) -eq 0
        echo "Usage: compress-video <input_video>"
        echo "Compresses video to 1280px width, 15fps, HEVC format with 1.5Mbps bitrate"
        return 1
    end

    set input_file $argv[1]

    if not test -f "$input_file"
        echo "Error: File '$input_file' not found"
        return 1
    end

    # Generate output filename by replacing extension with _small.mp4
    set output_file (string replace -r '\.[^.]+$' '_small.mp4' "$input_file")

    # If the input doesn't have an extension, just append _small.mp4
    if test "$output_file" = "$input_file"
        set output_file "$input_file"_small.mp4
    end

    echo "Compressing: $input_file"
    echo "Output: $output_file"

    ffmpeg -i "$input_file" \
        -vf "scale=1280:-1,fps=15" \
        -c:v hevc_videotoolbox \
        -b:v 1.5M \
        -tag:v hvc1 \
        -c:a copy \
        "$output_file"

    if test $status -eq 0
        echo "✓ Compression complete: $output_file"
        # Show file size comparison
        set input_size (du -h "$input_file" | cut -f1)
        set output_size (du -h "$output_file" | cut -f1)
        echo "Size: $input_size → $output_size"
    else
        echo "✗ Compression failed"
        return 1
    end
end