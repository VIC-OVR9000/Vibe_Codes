import matplotlib.pyplot as plt

# 1. Create a small window (4 inches wide by 3 inches high)
plt.figure(figsize=(4, 3))

# 2. Add mathematical text using raw strings (r"") and dollar signs ($)
# This example displays the quadratic formula
math_equation = r'$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$'

# Position the text in the center of the plot
plt.text(0.5, 0.5, math_equation,
         fontsize=20,
         ha='center',
         va='center')

# 3. Clean up the plot (remove axes for a "window" look)
plt.axis('off')
plt.title("Mathematical Result")

# 4. Display the window
plt.show()
