#version 330 core

layout(location = 0) out vec4 color;

uniform sampler2D[10] u_textures;
uniform float u_near = 0.1;  // Near plane distance
uniform float u_far = 100.0; // Far plane distance

in vec2 f_uv;
in float f_tex;

// ============================================================================
// Depth Visualization Methods
// ============================================================================

// Method 1: Linear depth (most popular - good general purpose visualization)
float linearizeDepth(float depth) {
    float z = depth * 2.0 - 1.0; // Convert to NDC space [-1, 1]
    return (2.0 * u_near * u_far) / (u_far + u_near - z * (u_far - u_near));
}

// Method 2: Logarithmic depth (better for large scenes with huge depth ranges)
float logDepth(float depth) {
    float linear = linearizeDepth(depth);
    return log(linear / u_near) / log(u_far / u_near);
}

// Method 3: Enhanced contrast depth (amplifies mid-range values)
float contrastDepth(float depth) {
    float linear = linearizeDepth(depth) / u_far; // Normalize to [0, 1]
    return pow(linear, 0.5); // Apply gamma correction for better contrast
}

// Method 4: Color-coded depth (heat map style - closest=red, far=blue)
vec3 depthHeatMap(float depth) {
    float linear = linearizeDepth(depth) / u_far; // Normalize to [0, 1]

    // Create a heat map: red (near) -> yellow -> green -> cyan -> blue (far)
    vec3 near_color = vec3(1.0, 0.0, 0.0);    // Red
    vec3 mid1_color = vec3(1.0, 1.0, 0.0);    // Yellow
    vec3 mid2_color = vec3(0.0, 1.0, 0.0);    // Green
    vec3 mid3_color = vec3(0.0, 1.0, 1.0);    // Cyan
    vec3 far_color = vec3(0.0, 0.0, 1.0);     // Blue

    vec3 result;
    if (linear < 0.25) {
        result = mix(near_color, mid1_color, linear * 4.0);
    } else if (linear < 0.5) {
        result = mix(mid1_color, mid2_color, (linear - 0.25) * 4.0);
    } else if (linear < 0.75) {
        result = mix(mid2_color, mid3_color, (linear - 0.5) * 4.0);
    } else {
        result = mix(mid3_color, far_color, (linear - 0.75) * 4.0);
    }

    return result;
}

void main() {

    color = texture(u_textures[int(f_tex)], f_uv) * sin(gl_FragCoord.x / 2.0);

    // Get raw depth from depth buffer
    float depth = texture(u_textures[1], f_uv).r;

    // ========================================================================
    // Choose your depth visualization method:
    // ========================================================================

    // Method 1: Linear depth (RECOMMENDED - most commonly used)
    float linearDepth = linearizeDepth(depth) / u_far; // Normalize to [0, 1]
    color = vec4(vec3(linearDepth), 1.0);

    // Method 2: Logarithmic depth (uncomment to use)
    // float logD = logDepth(depth);
    // color = vec4(vec3(logD), 1.0);

    // Method 3: Enhanced contrast (uncomment to use)
    // float contrast = contrastDepth(depth);
    // color = vec4(vec3(contrast), 1.0);

    // Method 4: Color heat map (uncomment to use)
    // vec3 heatMap = depthHeatMap(depth);
    // color = vec4(heatMap, 1.0);

    // Method 5: Raw depth (original method - not recommended)
    // color = vec4(vec3(depth), 1.0);
}
